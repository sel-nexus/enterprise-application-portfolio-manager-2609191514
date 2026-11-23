"""Exercise application inventory using the real MongoDB engine."""

import os
from uuid import uuid4
import pytest
import pytest_asyncio
from bson import ObjectId
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
    found = await http.get(BASE, headers=admin, params={'search': 'lex', 'criticality': 'High'})
    assert found.status_code == 200 and found.json()['total'] == 1
    literal = await http.get(BASE, headers=admin, params={'search': '.*'})
    assert literal.status_code == 200 and literal.json()['total'] == 0
    updated = await http.put(f'{BASE}/{aid}', headers=admin, json={**data(pid), 'business_owner': 'Jordan'})
    assert updated.status_code == 200 and updated.json()['business_owner'] == 'Jordan'
    fetched = await http.get(f'{BASE}/{aid}', headers=admin)
    assert fetched.status_code == 200 and fetched.json()['business_owner'] == 'Jordan'
    assert (await db.applications.find_one({'name_key': 'payments'}))['business_owner'] == 'Jordan'
    assert (await http.put(f'{BASE}/{aid}/lifecycle', headers=admin, json={'lifecycle': 'Retired'})).status_code == 200
    listing = await http.get(BASE, headers=admin)
    assert listing.status_code == 200 and listing.json()['total'] == 0
    all_lifecycles = await http.get(BASE, headers=admin, params={'lifecycle': 'All'})
    assert all_lifecycles.status_code == 200 and all_lifecycles.json()['total'] == 1
    assert (await http.put(f'{BASE}/{aid}/lifecycle', headers=admin, json={'lifecycle': 'Gone'})).status_code == 422
    assert await db.audit.count_documents({'record': aid, 'action': {'$in': ['create', 'edit', 'lifecycle_change']}}) == 3
    assert (await http.get(f'{BASE}/invalid', headers=admin)).status_code == 404
    assert (await http.get(BASE, headers=admin, params={'page': 0})).status_code == 422
    assert (await http.get(BASE)).status_code == 401


async def test_scope_source_target_and_role_ceiling(env):
    http, db, headers = env
    admin = headers['administrator']
    one, two = await portfolio(http, admin, 'One'), await portfolio(http, admin, 'Two')
    first = await http.post(BASE, headers=admin, json=data(one))
    second = await http.post(BASE, headers=admin, json=data(two, 'Other'))
    assert first.status_code == 201 and second.status_code == 201
    a, b = first.json(), second.json()
    for role in ('portfolio_leader', 'engineer', 'read_only'):
        await db.users.update_one({'role': role}, {'$set': {'portfolio_ids': [one]}})
    for role in ('portfolio_leader', 'engineer'):
        h = headers[role]
        listing = await http.get(BASE, headers=h)
        assert listing.status_code == 200 and listing.json()['total'] == 1
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
    fetched = await http.get(f'{BASE}/{created.json()["id"]}', headers=headers['engineer'])
    assert fetched.status_code == 200 and fetched.json()['name'] == 'Owned service'
    assert (await http.post(BASE, headers=headers['engineer'], json=data(other, 'Outside'))).status_code == 403
    assert await db.applications.count_documents({'name_key': 'outside'}) == 0


async def test_pagination_archived_and_cascade(env):
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    first_response = await http.post(BASE, headers=admin, json=data(pid))
    second_response = await http.post(BASE, headers=admin, json=data(pid, 'Second'))
    assert first_response.status_code == 201 and second_response.status_code == 201
    first, second = first_response.json(), second_response.json()
    page = await http.get(BASE, headers=admin, params={'page_size': 1, 'page': 2})
    assert page.status_code == 200 and page.json()['total'] == 2
    await db.reviews.insert_many([{'application_id': first['id']}, {'application_id': second['id']}])
    await db.dependencies.insert_many([{'from_application_id': first['id'], 'to_application_id': second['id']}, {'from_application_id': second['id'], 'to_application_id': first['id']}, {'from_application_id': second['id'], 'to_application_id': second['id']}])
    assert (await http.delete(f'{BASE}/{first["id"]}', headers=admin)).status_code == 204
    assert await db.reviews.count_documents({}) == 1
    assert await db.dependencies.count_documents({}) == 1
    assert await db.audit.count_documents({'record': first['id'], 'action': 'delete'}) == 1
    archived = await http.post(f'/api/v1/portfolios/{pid}/archive', headers=admin)
    assert archived.status_code == 200
    listing = await http.get(BASE, headers=admin)
    assert listing.status_code == 200 and listing.json()['total'] == 0
    included = await http.get(BASE, headers=admin, params={'include_archived': True})
    assert included.status_code == 200 and included.json()['total'] == 1


async def test_identity_missing_fields_ids_and_operator_payloads(env):
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    payload = data(pid)
    for field in ('name', 'portfolio_id', 'tier'):
        assert (await http.post(BASE, headers=admin, json={k: v for k, v in payload.items() if k != field})).status_code == 422
    for patch in ({'name': {'$ne': None}}, {'portfolio_id': {'$gt': ''}}, {'tier': True}, {'tier': '1'}, {'tier': 0}, {'name': 'x' * 201}, {'description': 'x' * 4001}):
        assert (await http.post(BASE, headers=admin, json=payload | patch)).status_code == 422
    assert (await http.post(BASE, headers=admin, json=payload)).status_code == 201
    for identifier in ('not-an-object-id', '000000000000000000000000'):
        assert (await http.get(f'{BASE}/{identifier}', headers=admin)).status_code == 404
        assert (await http.put(f'{BASE}/{identifier}', headers=admin, json=payload)).status_code == 404
        assert (await http.put(f'{BASE}/{identifier}/lifecycle', headers=admin, json={'lifecycle': 'Retired'})).status_code == 404
        assert (await http.delete(f'{BASE}/{identifier}', headers=admin)).status_code == 404
    for search in ('{"$ne":null}', '.*', '$where'):
        result = await http.get(BASE, headers=admin, params={'search': search})
        assert result.status_code == 200 and result.json()['total'] == 0
    assert await db.applications.count_documents({}) == 1


async def test_description_rejects_markup_without_losing_plain_text(env):
    """Reject markup on create and update, preserving ordinary descriptions."""
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    for attack in ('<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '<svg/onload=alert(1)>', '&lt;script&gt;alert(1)&lt;/script&gt;'):
        rejected = await http.post(BASE, headers=admin, json=data(pid) | {'description': attack})
        assert rejected.status_code == 422
        assert await db.applications.count_documents({}) == 0
    description = 'Latency < 5 ms & throughput > 100; contact A/B.'
    created = await http.post(BASE, headers=admin, json=data(pid) | {'description': description})
    assert created.status_code == 201 and created.json()['description'] == description
    aid = created.json()['id']
    rejected = await http.put(f'{BASE}/{aid}', headers=admin, json=data(pid) | {'description': '<script>alert(1)</script>'})
    assert rejected.status_code == 422
    fetched = await http.get(f'{BASE}/{aid}', headers=admin)
    assert fetched.status_code == 200 and fetched.headers['content-type'].startswith('application/json')
    assert fetched.json()['description'] == description
    assert (await db.applications.find_one({'name_key': 'payments'}))['description'] == description

    # Legacy records remain readable, but are still untrusted at the output boundary.
    await db.applications.update_one({'name_key': 'payments'}, {'$set': {'description': '<script>legacy</script>'}})
    legacy = await http.get(f'{BASE}/{aid}', headers=admin)
    assert legacy.status_code == 200 and legacy.json()['description'] == '<script>legacy</script>'


@pytest.mark.parametrize('field,limit', [
    ('product_area', 200), ('business_owner', 200), ('technology_owner', 200),
    ('inventory_owner', 200), ('technology_stack', 2000),
])
@pytest.mark.parametrize('invalid', [None, 123, True, [], {'$ne': None}, 'too_long'])
async def test_optional_identity_fields_reject_invalid_values_without_writes(env, field, limit, invalid):
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    value = 'x' * (limit + 1) if invalid == 'too_long' else invalid
    audit_before = await db.audit.count_documents({})
    rejected = await http.post(BASE, headers=admin, json=data(pid) | {field: value})
    assert rejected.status_code == 422
    assert await db.applications.count_documents({}) == 0
    assert await db.audit.count_documents({}) == audit_before

    created = await http.post(BASE, headers=admin, json=data(pid))
    assert created.status_code == 201
    identifier = created.json()['id']
    before = await db.applications.find_one({'_id': ObjectId(identifier)})
    audit_before = await db.audit.count_documents({})
    rejected = await http.put(f'{BASE}/{identifier}', headers=admin, json=data(pid) | {field: value})
    assert rejected.status_code == 422
    assert await db.applications.find_one({'_id': ObjectId(identifier)}) == before
    assert await db.applications.count_documents({}) == 1
    assert await db.audit.count_documents({}) == audit_before


@pytest.mark.parametrize('field,limit', [
    ('product_area', 200), ('business_owner', 200), ('technology_owner', 200),
    ('inventory_owner', 200), ('technology_stack', 2000),
])
@pytest.mark.parametrize('case', ['empty', 'whitespace', 'maximum', 'omitted'])
async def test_optional_identity_fields_persist_valid_boundaries_on_create_and_update(env, field, limit, case):
    http, db, headers = env
    admin = headers['administrator']
    pid = await portfolio(http, admin)
    payload = data(pid)
    if case == 'omitted':
        del payload[field]
        expected = ''
    else:
        payload[field] = {'empty': '', 'whitespace': '   ', 'maximum': 'x' * limit}[case]
        expected = 'x' * limit if case == 'maximum' else ''
    created = await http.post(BASE, headers=admin, json=payload)
    assert created.status_code == 201 and created.json()[field] == expected
    identifier = created.json()['id']
    assert (await db.applications.find_one({'_id': ObjectId(identifier)}))[field] == expected

    baseline = await http.put(f'{BASE}/{identifier}', headers=admin, json=data(pid) | {field: 'Before'})
    assert baseline.status_code == 200 and baseline.json()[field] == 'Before'
    assert (await db.applications.find_one({'_id': ObjectId(identifier)}))[field] == 'Before'
    if case == 'maximum':
        payload[field] = 'y' * limit
        expected = 'y' * limit
    updated = await http.put(f'{BASE}/{identifier}', headers=admin, json=payload)
    assert updated.status_code == 200 and updated.json()[field] == expected
    assert (await db.applications.find_one({'_id': ObjectId(identifier)}))[field] == expected
