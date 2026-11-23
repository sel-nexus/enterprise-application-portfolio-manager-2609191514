"""Exercise portfolio operations and access boundaries against real MongoDB."""

import os
from uuid import uuid4
import pytest
import pytest_asyncio
from bson import ObjectId
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
    search = await http.get(BASE, headers=admin, params={'search': 'orga'})
    assert search.status_code == 200
    assert search.json()['total'] == 1
    search = await http.get(BASE, headers=admin, params={'search': '.*'})
    assert search.status_code == 200
    assert search.json()['total'] == 0
    detail = await http.get(BASE + '/' + item['id'], headers=admin)
    assert detail.status_code == 200
    assert detail.json()['owner'] == 'Morgan'
    edited = await http.put(BASE + '/' + item['id'], headers=admin, json={**DATA, 'owner': 'Alex'})
    assert edited.status_code == 200 and edited.json()['owner'] == 'Alex'
    archived = await http.post(BASE + '/' + item['id'] + '/archive', headers=admin)
    assert archived.status_code == 200 and archived.json()['status'] == 'Archived'
    listing = await http.get(BASE, headers=admin)
    assert listing.status_code == 200
    assert listing.json()['total'] == 0
    listing = await http.get(BASE, headers=admin, params={'status': 'All'})
    assert listing.status_code == 200
    assert listing.json()['total'] == 1
    assert await db.audit.count_documents({'record': item['id'], 'action': {'$in': ['create', 'edit', 'archive']}}) == 3
    assert (await db.portfolios.find_one({'name_key': 'payments'}))['owner'] == 'Alex'
    assert (await http.get(BASE + '/invalid', headers=admin)).status_code == 404
    assert (await http.get(BASE, headers=admin, params={'page': 0})).status_code == 422
    assert (await http.get(BASE)).status_code == 401


async def test_leader_self_assignment_and_scope(env):
    http, db, headers = env
    leader = headers['portfolio_leader']
    response = await http.post(BASE, headers=leader, json=DATA)
    assert response.status_code == 201
    own = response.json()
    response = await http.post(BASE, headers=headers['administrator'], json={**DATA, 'name': 'Other'})
    assert response.status_code == 201
    other = response.json()
    assert own['id'] in (await db.users.find_one({'role': 'portfolio_leader'}))['portfolio_ids']
    response = await http.get(BASE, headers=leader)
    assert response.status_code == 200
    assert response.json()['total'] == 1
    assert (await http.get(BASE + '/' + other['id'], headers=leader)).status_code == 403
    assert (await http.put(BASE + '/' + other['id'], headers=leader, json=DATA)).status_code == 403
    assert (await http.post(BASE + '/' + own['id'] + '/archive', headers=leader)).status_code == 200
    assert (await http.delete(BASE + '/' + own['id'], headers=leader)).status_code == 403
    for role in ('engineer', 'read_only'):
        response = await http.get(BASE, headers=headers[role])
        assert response.status_code == 200
        assert response.json()['total'] == 0
        assert (await http.post(BASE, headers=headers[role], json={**DATA, 'name': role})).status_code == 403
    for role in ('executive', 'auditor'):
        response = await http.get(BASE, headers=headers[role], params={'status': 'All'})
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert (await http.post(BASE, headers=headers[role], json=DATA)).status_code == 403
    await db.roles.insert_one({'name': 'portfolio_leader', 'permissions': {'view': False, 'create': False, 'edit': False}})
    assert (await http.get(BASE, headers=leader)).status_code == 403
    assert (await http.post(BASE, headers=leader, json=DATA)).status_code == 403


async def test_delete_blocked_by_applications_and_unique_update(env):
    http, db, headers = env
    admin = headers['administrator']
    response = await http.post(BASE, headers=admin, json=DATA)
    assert response.status_code == 201
    one = response.json()
    response = await http.post(BASE, headers=admin, json={**DATA, 'name': 'Other'})
    assert response.status_code == 201
    two = response.json()
    assert (await http.put(BASE + '/' + two['id'], headers=admin, json={**DATA, 'name': 'PAYMENTS'})).status_code == 409
    await db.applications.insert_one({'name': 'Example', 'portfolio_id': one['id'], 'lifecycle': 'Retired'})
    response = await http.get(BASE + '/' + one['id'], headers=admin)
    assert response.status_code == 200
    assert response.json()['application_count'] == 1
    assert (await http.delete(BASE + '/' + one['id'], headers=admin)).status_code == 409
    assert await db.portfolios.count_documents({'name_key': 'payments'}) == 1
    assert (await http.delete(BASE + '/' + two['id'], headers=admin)).status_code == 204
    assert (await http.get(BASE + '/' + two['id'], headers=admin)).status_code == 404
    assert await db.audit.count_documents({'record': two['id'], 'action': 'delete'}) == 1


async def test_missing_ids_required_fields_and_query_injection(env):
    http, db, headers = env
    admin = headers['administrator']
    for field in ('name', 'owner', 'product_area'):
        assert (await http.post(BASE, headers=admin, json={k: v for k, v in DATA.items() if k != field})).status_code == 422
    for patch in ({'name': {'$ne': None}}, {'name': 'x' * 201}, {'description': 'x' * 4001}, {'owner': None}):
        assert (await http.post(BASE, headers=admin, json=DATA | patch)).status_code == 422
    created = await http.post(BASE, headers=admin, json=DATA)
    assert created.status_code == 201
    for identifier in ('not-an-object-id', '000000000000000000000000'):
        assert (await http.get(f'{BASE}/{identifier}', headers=admin)).status_code == 404
        assert (await http.put(f'{BASE}/{identifier}', headers=admin, json=DATA)).status_code == 404
        assert (await http.delete(f'{BASE}/{identifier}', headers=admin)).status_code == 404
        assert (await http.post(f'{BASE}/{identifier}/archive', headers=admin)).status_code == 404
    for query in ('{"$ne":null}', '.*', '$where'):
        result = await http.get(BASE, headers=admin, params={'search': query})
        assert result.status_code == 200 and result.json()['total'] == 0
    assert await db.portfolios.count_documents({}) == 1


@pytest.mark.parametrize('invalid', [None, '', '   ', 123, True, [], {'$ne': None}, 'x' * 201])
async def test_product_area_invalid_on_create_and_update_does_not_write(env, invalid):
    http, db, headers = env
    admin = headers['administrator']
    rejected = await http.post(BASE, headers=admin, json=DATA | {'product_area': invalid})
    assert rejected.status_code == 422
    assert await db.portfolios.count_documents({}) == 0
    assert await db.audit.count_documents({}) == 0

    created = await http.post(BASE, headers=admin, json=DATA)
    assert created.status_code == 201
    identifier = created.json()['id']
    before = await db.portfolios.find_one({'_id': ObjectId(identifier)})
    audit_before = await db.audit.count_documents({})
    rejected = await http.put(f'{BASE}/{identifier}', headers=admin, json=DATA | {'product_area': invalid})
    assert rejected.status_code == 422
    assert await db.portfolios.find_one({'_id': ObjectId(identifier)}) == before
    assert await db.portfolios.count_documents({}) == 1
    assert await db.audit.count_documents({}) == audit_before


async def test_product_area_exactly_200_characters_is_persisted(env):
    http, db, headers = env
    value = 'x' * 200
    response = await http.post(BASE, headers=headers['administrator'], json=DATA | {'product_area': value})
    assert response.status_code == 201
    assert response.json()['product_area'] == value
    identifier = response.json()['id']
    assert (await db.portfolios.find_one({'_id': ObjectId(identifier)}))['product_area'] == value
    updated = 'y' * 200
    response = await http.put(f'{BASE}/{identifier}', headers=headers['administrator'], json=DATA | {'product_area': updated})
    assert response.status_code == 200
    assert response.json()['product_area'] == updated
    assert (await db.portfolios.find_one({'_id': ObjectId(identifier)}))['product_area'] == updated


@pytest.mark.parametrize('invalid', [None, '', '   ', 123, True, [], {'$ne': None}, 'x' * 201])
async def test_owner_invalid_on_create_and_update_does_not_write(env, invalid):
    http, db, headers = env
    admin = headers['administrator']
    rejected = await http.post(BASE, headers=admin, json=DATA | {'owner': invalid})
    assert rejected.status_code == 422
    assert await db.portfolios.count_documents({}) == 0
    assert await db.audit.count_documents({}) == 0

    created = await http.post(BASE, headers=admin, json=DATA)
    assert created.status_code == 201
    identifier = created.json()['id']
    before = await db.portfolios.find_one({'_id': ObjectId(identifier)})
    audit_before = await db.audit.count_documents({})
    rejected = await http.put(f'{BASE}/{identifier}', headers=admin, json=DATA | {'owner': invalid})
    assert rejected.status_code == 422
    assert await db.portfolios.find_one({'_id': ObjectId(identifier)}) == before
    assert await db.portfolios.count_documents({}) == 1
    assert await db.audit.count_documents({}) == audit_before


async def test_owner_missing_on_update_does_not_write(env):
    http, db, headers = env
    admin = headers['administrator']
    created = await http.post(BASE, headers=admin, json=DATA)
    assert created.status_code == 201
    identifier = created.json()['id']
    before = await db.portfolios.find_one({'_id': ObjectId(identifier)})
    audit_before = await db.audit.count_documents({})
    rejected = await http.put(f'{BASE}/{identifier}', headers=admin, json={k: v for k, v in DATA.items() if k != 'owner'})
    assert rejected.status_code == 422
    assert await db.portfolios.find_one({'_id': ObjectId(identifier)}) == before
    assert await db.audit.count_documents({}) == audit_before


async def test_owner_exactly_200_characters_is_persisted(env):
    http, db, headers = env
    admin = headers['administrator']
    value = 'x' * 200
    created = await http.post(BASE, headers=admin, json=DATA | {'owner': value})
    assert created.status_code == 201 and created.json()['owner'] == value
    identifier = created.json()['id']
    assert (await db.portfolios.find_one({'_id': ObjectId(identifier)}))['owner'] == value
    updated = 'y' * 200
    response = await http.put(f'{BASE}/{identifier}', headers=admin, json=DATA | {'owner': updated})
    assert response.status_code == 200 and response.json()['owner'] == updated
    assert (await db.portfolios.find_one({'_id': ObjectId(identifier)}))['owner'] == updated
