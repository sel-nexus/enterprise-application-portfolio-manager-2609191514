"""Exercise portfolio operations and access boundaries against real MongoDB."""

import os
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.core.config import settings
from app.main import app
from app.portfolios.repository import PortfolioRepository

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/portfolios'
DATA = {'name': 'Payments', 'owner': 'Morgan', 'product_area': 'Finance', 'description': 'Core payments', 'status': 'Active'}


@pytest_asyncio.fixture
async def env():
    """Create an isolated test database and authenticated accounts."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'portfolios_test_' + uuid4().hex
    db = mongo[name]
    settings.jwt_secret = 'test-only-' + uuid4().hex + uuid4().hex
    app.state.db = db
    accounts = AccountRepository(db)
    await accounts.indexes()
    await PortfolioRepository(db).indexes()
    headers = {}
    for role in ('administrator', 'portfolio_leader', 'engineer', 'executive', 'auditor', 'read_only'):
        doc = {'name': role, 'email': role + '@example.com', 'role': role, 'active': True, 'portfolio_ids': [], 'must_change_password': False, 'token_version': 0}
        doc['_id'] = (await db.users.insert_one(doc)).inserted_id
        token = await AccountService(accounts).issue(doc, 'access')
        headers[role] = {'Authorization': 'Bearer ' + token.access_token}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, db, headers
    finally:
        await mongo.drop_database(name)
        await mongo.close()


async def test_create_search_edit_archive_and_audit(env):
    http, db, headers = env
    admin = headers['administrator']
    created = await http.post(BASE, headers=admin, json=DATA)
    assert created.status_code == 201
    item = created.json()
    assert item['name'] == 'Payments' and item['application_count'] == 0
    assert (await http.post(BASE, headers=admin, json={**DATA, 'name': '  payments  '})).status_code == 409
    assert (await http.post(BASE, headers=admin, json={**DATA, 'owner': '   '})).status_code == 422
    assert (await http.post(BASE, headers=admin, json={**DATA, 'status': 'bad'})).status_code == 422
    assert (await http.get(BASE, headers=admin, params={'search': 'orga'})).json()['total'] == 1
    assert (await http.get(BASE, headers=admin, params={'search': '.*'})).json()['total'] == 0
    assert (await http.get(BASE + '/' + item['id'], headers=admin)).json()['owner'] == 'Morgan'
    edited = await http.put(BASE + '/' + item['id'], headers=admin, json={**DATA, 'owner': 'Alex'})
    assert edited.status_code == 200 and edited.json()['owner'] == 'Alex'
    archived = await http.post(BASE + '/' + item['id'] + '/archive', headers=admin)
    assert archived.status_code == 200 and archived.json()['status'] == 'Archived'
    assert (await http.get(BASE, headers=admin)).json()['total'] == 0
    assert (await http.get(BASE, headers=admin, params={'status': 'All'})).json()['total'] == 1
    assert await db.audit.count_documents({'record': item['id'], 'action': {'$in': ['create', 'edit', 'archive']}}) == 3
    assert (await db.portfolios.find_one({'name_key': 'payments'}))['owner'] == 'Alex'
    assert (await http.get(BASE + '/invalid', headers=admin)).status_code == 404
    assert (await http.get(BASE, headers=admin, params={'page': 0})).status_code == 422
    assert (await http.get(BASE)).status_code == 401


async def test_leader_self_assignment_and_scope(env):
    http, db, headers = env
    leader = headers['portfolio_leader']
    own = (await http.post(BASE, headers=leader, json=DATA)).json()
    other = (await http.post(BASE, headers=headers['administrator'], json={**DATA, 'name': 'Other'})).json()
    assert own['id'] in (await db.users.find_one({'role': 'portfolio_leader'}))['portfolio_ids']
    assert (await http.get(BASE, headers=leader)).json()['total'] == 1
    assert (await http.get(BASE + '/' + other['id'], headers=leader)).status_code == 403
    assert (await http.put(BASE + '/' + other['id'], headers=leader, json=DATA)).status_code == 403
    assert (await http.post(BASE + '/' + own['id'] + '/archive', headers=leader)).status_code == 200
    assert (await http.delete(BASE + '/' + own['id'], headers=leader)).status_code == 403
    for role in ('engineer', 'read_only'):
        assert (await http.get(BASE, headers=headers[role])).json()['total'] == 0
        assert (await http.post(BASE, headers=headers[role], json={**DATA, 'name': role})).status_code == 403
    for role in ('executive', 'auditor'):
        assert (await http.get(BASE, headers=headers[role], params={'status': 'All'})).json()['total'] == 2
        assert (await http.post(BASE, headers=headers[role], json=DATA)).status_code == 403
    await db.roles.insert_one({'name': 'portfolio_leader', 'permissions': {'view': False, 'create': False, 'edit': False}})
    assert (await http.get(BASE, headers=leader)).status_code == 403
    assert (await http.post(BASE, headers=leader, json=DATA)).status_code == 403


async def test_delete_blocked_by_applications_and_unique_update(env):
    http, db, headers = env
    admin = headers['administrator']
    one = (await http.post(BASE, headers=admin, json=DATA)).json()
    two = (await http.post(BASE, headers=admin, json={**DATA, 'name': 'Other'})).json()
    assert (await http.put(BASE + '/' + two['id'], headers=admin, json={**DATA, 'name': 'PAYMENTS'})).status_code == 409
    await db.applications.insert_one({'name': 'Example', 'portfolio_id': one['id'], 'lifecycle': 'Retired'})
    assert (await http.get(BASE + '/' + one['id'], headers=admin)).json()['application_count'] == 1
    assert (await http.delete(BASE + '/' + one['id'], headers=admin)).status_code == 409
    assert await db.portfolios.count_documents({'name_key': 'payments'}) == 1
    assert (await http.delete(BASE + '/' + two['id'], headers=admin)).status_code == 204
    assert (await http.get(BASE + '/' + two['id'], headers=admin)).status_code == 404
    assert await db.audit.count_documents({'record': two['id'], 'action': 'delete'}) == 1
