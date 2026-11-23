"""Exercise directional links through the API against real MongoDB."""
import os
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.core.config import settings
from app.dependencies.repository import DependencyRepository
from app.main import app

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/dependencies'


@pytest_asyncio.fixture
async def env():
    """Provision an isolated database and authenticated accounts."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'dependencies_test_' + uuid4().hex
    db = mongo[name]
    settings.jwt_secret = 'test-only-' + uuid4().hex * 2
    app.state.db = db
    repo = AccountRepository(db)
    await repo.indexes()
    await DependencyRepository(db).indexes()
    headers, users = {}, {}
    for role in ('administrator', 'engineer', 'read_only', 'executive'):
        user = {'name': role, 'email': role + '@example.com', 'role': role, 'active': True, 'portfolio_ids': [], 'must_change_password': False, 'token_version': 0}
        user['_id'] = (await db.users.insert_one(user)).inserted_id
        users[role] = user
        token = await AccountService(repo).issue(user, 'access')
        headers[role] = {'Authorization': 'Bearer ' + token.access_token}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, db, headers, users
    finally:
        await mongo.drop_database(name)
        await mongo.close()


async def estate(db, name, lifecycle='Active'):
    """Insert an application and its portfolio."""
    pid = str((await db.portfolios.insert_one({'name': name, 'status': 'Active'})).inserted_id)
    aid = str((await db.applications.insert_one({'name': name + ' app', 'portfolio_id': pid, 'lifecycle': lifecycle})).inserted_id)
    return pid, aid


def payload(source, target, relationship='Calls'):
    """Build a valid dependency request."""
    return {'from_application_id': source, 'to_application_id': target, 'relationship': relationship, 'note': 'Interface'}


async def test_create_validation_uniqueness_and_audit(env):
    """Reject invalid and duplicate triples while preserving direction and type."""
    http, db, headers, _ = env
    _, a = await estate(db, 'Alpha')
    _, b = await estate(db, 'Beta')
    admin = headers['administrator']
    assert (await http.post(BASE, json=payload(a, b))).status_code == 401
    assert (await http.post(BASE, headers=admin, json=payload(a, a))).status_code == 422
    assert (await http.post(BASE, headers=admin, json=payload(a.upper(), a))).status_code == 422
    assert (await http.post(BASE, headers=admin, json=payload(a, b, 'invalid'))).status_code == 422
    assert (await http.post(BASE, headers=admin, json=payload(a, 'missing'))).status_code == 404
    assert (await http.post(BASE, headers=admin, json=payload(a, b) | {'note': 'x' * 2001})).status_code == 422
    created = await http.post(BASE, headers=admin, json=payload(a, b))
    assert created.status_code == 201
    duplicate = await http.post(BASE, headers=admin, json=payload(a.upper(), b.upper()))
    assert duplicate.status_code == 409 and duplicate.json()['detail'] == 'That dependency is already recorded.'
    assert (await http.post(BASE, headers=admin, json=payload(a, b, 'Needs at runtime'))).status_code == 201
    assert (await http.post(BASE, headers=admin, json=payload(b, a))).status_code == 201
    assert await db.dependencies.count_documents({'from_application_id': a, 'to_application_id': b}) == 2
    assert await db.audit.count_documents({'action': 'dependency_added'}) == 3


async def test_required_dependency_fields_types_and_limits(env):
    """Validate each request field before persisting a link."""
    http, db, headers, _ = env
    _, a = await estate(db, 'Alpha')
    _, b = await estate(db, 'Beta')
    valid = payload(a, b)
    for field in ('from_application_id', 'to_application_id', 'relationship'):
        response = await http.post(BASE, headers=headers['administrator'], json={k: v for k, v in valid.items() if k != field})
        assert response.status_code == 422
    for field in ('from_application_id', 'to_application_id', 'relationship', 'note'):
        for invalid in (None, 123, {'$ne': None}, []):
            response = await http.post(BASE, headers=headers['administrator'], json=valid | {field: invalid})
            assert response.status_code == 422
    for patch in ({'from_application_id': ''}, {'to_application_id': ''}, {'relationship': ''},
                  {'from_application_id': 'a' * 25}, {'to_application_id': 'b' * 25}, {'note': 'x' * 2001}):
        assert (await http.post(BASE, headers=headers['administrator'], json=valid | patch)).status_code == 422
    assert await db.dependencies.count_documents({}) == 0
    created = await http.post(BASE, headers=headers['administrator'], json=valid | {'note': 'x' * 2000})
    assert created.status_code == 201 and created.json()['note'] == 'x' * 2000
    assert await db.dependencies.count_documents({}) == 1


async def test_scope_and_permissions_on_both_endpoints(env):
    """Do not disclose links whose other endpoint is outside scope."""
    http, db, headers, users = env
    pid, a = await estate(db, 'Alpha')
    _, b = await estate(db, 'Beta')
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    await db.users.update_one({'_id': users['read_only']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    admin, engineer, reader = (headers[x] for x in ('administrator', 'engineer', 'read_only'))
    created = await http.post(BASE, headers=admin, json=payload(a, b))
    link = created.json()['id']
    assert (await http.post(BASE, headers=engineer, json=payload(a, b))).status_code == 403
    assert (await http.post(BASE, headers=engineer, json=payload(b, a))).status_code == 403
    assert (await http.post(BASE, headers=reader, json=payload(a, a))).status_code == 403
    assert (await http.delete(f'{BASE}/{link}', headers=engineer)).status_code == 403
    assert (await http.get(BASE, headers=engineer)).json()['total'] == 0
    assert (await http.get(BASE, headers=engineer, params={'application_id': b})).status_code == 403
    assert (await http.get(BASE, headers=headers['executive'])).json()['total'] == 1
    await db.roles.insert_one({'name': 'administrator', 'permissions': {'view': True, 'edit': False}})
    assert (await http.delete(f'{BASE}/{link}', headers=admin)).status_code == 403
    assert await db.dependencies.count_documents({}) == 1


async def test_views_filters_pagination_summary_removal_and_cascade(env):
    """Recompute both directional views and chart after removal and application deletion."""
    http, db, headers, _ = env
    admin = headers['administrator']
    pa, a = await estate(db, 'Alpha')
    pb, b = await estate(db, 'Beta')
    _, c = await estate(db, 'Gamma', 'Deprecated')
    _, retired = await estate(db, 'Retired', 'Retired')
    first = (await http.post(BASE, headers=admin, json=payload(a, b))).json()['id']
    second = (await http.post(BASE, headers=admin, json=payload(c, b, 'Receives data from'))).json()['id']
    all_links = (await http.get(BASE, headers=admin, params={'page_size': 1})).json()
    assert all_links['total'] == 2 and len(all_links['items']) == 1
    assert all_links['chart'][0]['application_id'] == b and all_links['chart'][0]['count'] == 2
    assert all_links['unlinked_count'] == 0
    assert (await http.get(BASE, headers=admin, params={'application_id': a})).json()['total'] == 1
    assert (await http.get(BASE, headers=admin, params={'application_id': b, 'direction': 'incoming'})).json()['total'] == 2
    assert (await http.get(BASE, headers=admin, params={'relationship': 'Calls', 'portfolio_id': pb, 'search': 'Alpha'})).json()['total'] == 1
    assert (await http.get(BASE, headers=admin, params={'portfolio_id': pa})).json()['total'] == 0
    assert (await http.get(BASE, headers=admin, params={'page_size': 101})).status_code == 422
    assert (await http.delete(f'{BASE}/{first}', headers=admin)).status_code == 204
    assert (await http.delete(f'{BASE}/{first}', headers=admin)).status_code == 404
    updated = (await http.get(BASE, headers=admin)).json()
    assert updated['chart'][0]['count'] == 1 and updated['unlinked_count'] == 1
    assert (await http.get(BASE, headers=admin, params={'application_id': a})).json()['total'] == 0
    assert (await http.get(BASE, headers=admin, params={'application_id': b, 'direction': 'incoming'})).json()['total'] == 1
    assert await db.audit.count_documents({'action': 'dependency_removed'}) == 1
    assert (await http.delete(f'/api/v1/applications/{b}', headers=admin)).status_code == 204
    assert await db.dependencies.count_documents({}) == 0
    assert (await http.get(BASE, headers=admin)).json()['chart'] == []
    assert second and retired
