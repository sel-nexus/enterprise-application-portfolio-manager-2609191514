"""Exercise application inventory using the real MongoDB engine."""

import os
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.applications.repository import ApplicationRepository
from app.core.config import settings
from app.main import app
from app.portfolios.repository import PortfolioRepository

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/applications'


@pytest_asyncio.fixture
async def env():
    """Set up a dedicated database and real authenticated sessions."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'applications_test_' + uuid4().hex
    db = mongo[name]
    settings.jwt_secret = 'test-only-' + uuid4().hex + uuid4().hex
    app.state.db = db
    accounts = AccountRepository(db)
    await accounts.indexes()
    await PortfolioRepository(db).indexes()
    await ApplicationRepository(db).indexes()
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


async def portfolio(http, headers, name='Finance'):
    """Create an active portfolio through the API."""
    response = await http.post('/api/v1/portfolios', headers=headers, json={'name': name, 'owner': 'Morgan', 'product_area': 'Finance'})
    assert response.status_code == 201
    return response.json()['id']


def data(portfolio_id, name='Payments'):
    """Build a valid application identity."""
    return {'name': name, 'portfolio_id': portfolio_id, 'description': 'Core service', 'product_area': 'Finance', 'business_owner': 'Alex', 'technology_owner': 'Sam', 'inventory_owner': 'Lee', 'criticality': 'High', 'tier': 1, 'technology_stack': 'Python'}


async def test_identity_lifecycle_persistence_and_validation(env):
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    created = await http.post(BASE, headers=admin, json=data(pid))
    assert created.status_code == 201
    item = created.json()
    aid = item['id']
    assert item['lifecycle'] == 'Active' and item['portfolio_name'] == 'Finance'
    assert (await http.post(BASE, headers=admin, json=data(pid, ' payments '))).status_code == 409
    assert (await http.post(BASE, headers=admin, json={**data(pid), 'tier': 5})).status_code == 422
    assert (await http.post(BASE, headers=admin, json={**data(pid), 'name': ' ', 'tier': 1})).status_code == 422
    assert (await http.post(BASE, headers=admin, json={**data(pid), 'quality': 80})).status_code == 422
    assert (await http.get(BASE, headers=admin, params={'search': 'lex', 'criticality': 'High'})).json()['total'] == 1
    assert (await http.get(BASE, headers=admin, params={'search': '.*'})).json()['total'] == 0
    assert (await http.put(f'{BASE}/{aid}', headers=admin, json={**data(pid), 'business_owner': 'Jordan'})).json()['business_owner'] == 'Jordan'
    assert (await http.get(f'{BASE}/{aid}', headers=admin)).json()['business_owner'] == 'Jordan'
    assert (await db.applications.find_one({'name_key': 'payments'}))['business_owner'] == 'Jordan'
    assert (await http.put(f'{BASE}/{aid}/lifecycle', headers=admin, json={'lifecycle': 'Retired'})).status_code == 200
    assert (await http.get(BASE, headers=admin)).json()['total'] == 0
    assert (await http.get(BASE, headers=admin, params={'lifecycle': 'All'})).json()['total'] == 1
    assert (await http.put(f'{BASE}/{aid}/lifecycle', headers=admin, json={'lifecycle': 'Gone'})).status_code == 422
    assert await db.audit.count_documents({'record': aid, 'action': {'$in': ['create', 'edit', 'lifecycle_change']}}) == 3
    assert (await http.get(f'{BASE}/invalid', headers=admin)).status_code == 404
    assert (await http.get(BASE, headers=admin, params={'page': 0})).status_code == 422
    assert (await http.get(BASE)).status_code == 401


async def test_scope_source_target_and_role_ceiling(env):
    http, db, headers = env
    admin = headers['administrator']
    one, two = await portfolio(http, admin, 'One'), await portfolio(http, admin, 'Two')
    a = (await http.post(BASE, headers=admin, json=data(one))).json()
    b = (await http.post(BASE, headers=admin, json=data(two, 'Other'))).json()
    for role in ('portfolio_leader', 'engineer', 'read_only'):
        await db.users.update_one({'role': role}, {'$set': {'portfolio_ids': [one]}})
    for role in ('portfolio_leader', 'engineer'):
        h = headers[role]
        assert (await http.get(BASE, headers=h)).json()['total'] == 1
        assert (await http.get(f'{BASE}/{b["id"]}', headers=h)).status_code == 403
        assert (await http.put(f'{BASE}/{a["id"]}', headers=h, json=data(two))).status_code == 403
        assert (await http.put(f'{BASE}/{b["id"]}', headers=h, json=data(one, 'Other'))).status_code == 403
        assert (await http.post(BASE, headers=h, json=data(two, 'New'))).status_code == 403
        assert (await http.delete(f'{BASE}/{a["id"]}', headers=h)).status_code == 403
    for role in ('executive', 'auditor', 'read_only'):
        h = headers[role]
        assert (await http.post(BASE, headers=h, json=data(one, 'Denied'))).status_code == 403
        assert (await http.put(f'{BASE}/{a["id"]}/lifecycle', headers=h, json={'lifecycle': 'Retired'})).status_code == 403
    await db.roles.insert_one({'name': 'engineer', 'permissions': {'view': True, 'edit': False, 'create': False}})
    assert (await http.put(f'{BASE}/{a["id"]}', headers=headers['engineer'], json=data(one))).status_code == 403
    # A concurrent move must invalidate an earlier authorization decision.
    repo = ApplicationRepository(db)
    assert await repo.update(a['id'], {'portfolio_id': two}, one)
    assert await repo.update(a['id'], {'business_owner': 'Stale'}, one) is None
    assert (await repo.get(a['id']))['business_owner'] == 'Alex'


async def test_scoped_engineer_can_create_and_retrieve_assigned_application(env):
    """An engineer can create in an assigned portfolio but not an unassigned one."""
    http, db, headers = env
    admin = headers['administrator']
    allowed = await portfolio(http, admin, 'Allowed')
    other = await portfolio(http, admin, 'Restricted')
    await db.users.update_one({'role': 'engineer'}, {'$set': {'portfolio_ids': [allowed]}})
    created = await http.post(BASE, headers=headers['engineer'], json=data(allowed, 'Owned service'))
    assert created.status_code == 201
    assert (await http.get(f'{BASE}/{created.json()["id"]}', headers=headers['engineer'])).json()['name'] == 'Owned service'
    assert (await http.post(BASE, headers=headers['engineer'], json=data(other, 'Outside'))).status_code == 403
    assert await db.applications.count_documents({'name_key': 'outside'}) == 0


async def test_pagination_archived_and_cascade(env):
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    first = (await http.post(BASE, headers=admin, json=data(pid))).json()
    second = (await http.post(BASE, headers=admin, json=data(pid, 'Second'))).json()
    assert (await http.get(BASE, headers=admin, params={'page_size': 1, 'page': 2})).json()['total'] == 2
    await db.reviews.insert_many([{'application_id': first['id']}, {'application_id': second['id']}])
    await db.dependencies.insert_many([{'from_application_id': first['id'], 'to_application_id': second['id']}, {'from_application_id': second['id'], 'to_application_id': first['id']}, {'from_application_id': second['id'], 'to_application_id': second['id']}])
    assert (await http.delete(f'{BASE}/{first["id"]}', headers=admin)).status_code == 204
    assert await db.reviews.count_documents({}) == 1
    assert await db.dependencies.count_documents({}) == 1
    assert await db.audit.count_documents({'record': first['id'], 'action': 'delete'}) == 1
    await http.post(f'/api/v1/portfolios/{pid}/archive', headers=admin)
    assert (await http.get(BASE, headers=admin)).json()['total'] == 0
    assert (await http.get(BASE, headers=admin, params={'include_archived': True})).json()['total'] == 1
