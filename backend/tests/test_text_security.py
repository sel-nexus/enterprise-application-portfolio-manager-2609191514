"""Verify text write boundaries through the API and real MongoDB."""
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.admin.seed import seed_roles
from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio
ATTACKS = ('<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
           '<svg/onload=alert(1)>', '&lt;script&gt;alert(1)&lt;/script&gt;',
           '&#x3c;img src=x&#x3e;', '&amp;lt;svg/onload=alert(1)&amp;gt;')
PLAIN = 'Latency < 5 ms & throughput > 100; A/B'
PORTFOLIO = {'name': 'Finance', 'owner': 'Morgan', 'product_area': 'Payments', 'description': 'Core', 'status': 'Active'}
APPLICATION = {'name': 'Service', 'description': 'Core', 'product_area': 'Finance', 'business_owner': 'Alex', 'technology_owner': 'Sam', 'inventory_owner': 'Lee', 'tier': 1, 'technology_stack': 'Python'}
REVIEW = {'health': 50, 'quality': 50, 'automation_coverage': 50, 'unit_test_coverage': 50, 'open_defects': 2, 'open_critical_defects': 1, 'risk': 'Low', 'note': 'Checked'}
USER = {'name': 'Engineer', 'email': 'engineer@example.com', 'role': 'engineer', 'manager': 'Admin', 'portfolio_ids': [], 'temporary_password': 'Password123456'}


@pytest_asyncio.fixture
async def env():
    """Create an isolated Mongo database and an authenticated administrator."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'text_security_test_' + uuid4().hex
    db = mongo[name]
    previous_db = getattr(app.state, 'db', None)
    previous_secret = settings.jwt_secret
    settings.jwt_secret = 'test-only-' + uuid4().hex * 2
    app.state.db = db
    try:
        await mongo.admin.command('ping')
        await seed_roles(db)
        repo = AccountRepository(db)
        doc = {'name': 'Admin', 'email': 'admin@example.com', 'role': 'administrator', 'active': True, 'portfolio_ids': [], 'must_change_password': False, 'token_version': 0}
        doc['_id'] = (await db.users.insert_one(doc)).inserted_id
        token = await AccountService(repo).issue(doc, 'access')
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, db, {'Authorization': 'Bearer ' + token.access_token}
    finally:
        app.state.db = previous_db
        settings.jwt_secret = previous_secret
        await mongo.drop_database(name)
        await mongo.close()


@pytest.mark.parametrize('field', ['name', 'owner', 'product_area', 'description'])
async def test_portfolio_create_update_reject_markup_and_preserve_text(env, field):
    http, db, headers = env
    path = '/api/v1/portfolios'
    for attack in ATTACKS:
        response = await http.post(path, headers=headers, json=PORTFOLIO | {field: attack})
        assert response.status_code == 422
        assert await db.portfolios.count_documents({}) == 0
    created = await http.post(path, headers=headers, json=PORTFOLIO | {field: PLAIN})
    assert created.status_code == 201 and created.json()[field] == PLAIN
    identifier = created.json()['id']
    before = await db.portfolios.find_one({'_id': ObjectId(identifier)})
    for attack in ATTACKS:
        rejected = await http.put(f'{path}/{identifier}', headers=headers, json=PORTFOLIO | {field: attack})
        assert rejected.status_code == 422
        assert await db.portfolios.find_one({'_id': ObjectId(identifier)}) == before
    response = await http.get(f'{path}/{identifier}', headers=headers)
    assert response.status_code == 200
    assert response.json()[field] == PLAIN
    await db.portfolios.update_one({'_id': ObjectId(identifier)}, {'$set': {field: '<b>legacy</b>'}})
    legacy = await http.get(f'{path}/{identifier}', headers=headers)
    assert legacy.status_code == 200 and legacy.json()[field] == '<b>legacy</b>'


@pytest.mark.parametrize('field', ['name', 'description', 'product_area', 'business_owner', 'technology_owner', 'inventory_owner', 'technology_stack'])
async def test_application_create_update_reject_markup_and_preserve_text(env, field):
    http, db, headers = env
    portfolio = await http.post('/api/v1/portfolios', headers=headers, json=PORTFOLIO)
    assert portfolio.status_code == 201
    payload = APPLICATION | {'portfolio_id': portfolio.json()['id']}
    path = '/api/v1/applications'
    for attack in ATTACKS:
        assert (await http.post(path, headers=headers, json=payload | {field: attack})).status_code == 422
        assert await db.applications.count_documents({}) == 0
    created = await http.post(path, headers=headers, json=payload | {field: PLAIN})
    assert created.status_code == 201 and created.json()[field] == PLAIN
    identifier = created.json()['id']
    before = await db.applications.find_one({'_id': ObjectId(identifier)})
    for attack in ATTACKS:
        assert (await http.put(f'{path}/{identifier}', headers=headers, json=payload | {field: attack})).status_code == 422
        assert await db.applications.find_one({'_id': ObjectId(identifier)}) == before
    await db.applications.update_one({'_id': ObjectId(identifier)}, {'$set': {field: '<b>legacy</b>'}})
    legacy = await http.get(f'{path}/{identifier}', headers=headers)
    assert legacy.status_code == 200 and legacy.json()[field] == '<b>legacy</b>'


async def test_review_and_dependency_notes_reject_markup(env):
    http, db, headers = env
    portfolio = await http.post('/api/v1/portfolios', headers=headers, json=PORTFOLIO)
    assert portfolio.status_code == 201
    pid = portfolio.json()['id']
    first = await http.post('/api/v1/applications', headers=headers, json=APPLICATION | {'portfolio_id': pid})
    second = await http.post('/api/v1/applications', headers=headers, json=APPLICATION | {'portfolio_id': pid, 'name': 'Other'})
    assert first.status_code == 201
    assert second.status_code == 201
    a, b = first.json()['id'], second.json()['id']
    review_path = f'/api/v1/reviews/applications/{a}'
    dependency = {'from_application_id': a, 'to_application_id': b, 'relationship': 'Calls', 'note': PLAIN}
    for attack in ATTACKS:
        assert (await http.post(review_path, headers=headers, json=REVIEW | {'note': attack})).status_code == 422
        assert (await http.post('/api/v1/dependencies', headers=headers, json=dependency | {'note': attack})).status_code == 422
        assert await db.reviews.count_documents({}) == 0
        assert await db.dependencies.count_documents({}) == 0
    saved_review = await http.post(review_path, headers=headers, json=REVIEW | {'note': PLAIN})
    saved_dependency = await http.post('/api/v1/dependencies', headers=headers, json=dependency)
    assert saved_review.status_code == saved_dependency.status_code == 201
    assert (await db.reviews.find_one({}))['note'] == PLAIN
    assert (await db.dependencies.find_one({}))['note'] == PLAIN


@pytest.mark.parametrize('field', ['name', 'manager'])
async def test_admin_user_text_rejects_markup_on_create_and_update(env, field):
    http, db, headers = env
    path = '/api/v1/admin/users'
    for attack in ATTACKS:
        assert (await http.post(path, headers=headers, json=USER | {field: attack})).status_code == 422
        assert await db.users.count_documents({}) == 1
    created = await http.post(path, headers=headers, json=USER | {field: PLAIN})
    assert created.status_code == 201 and created.json()[field] == PLAIN
    identifier = created.json()['id']
    before = await db.users.find_one({'_id': ObjectId(identifier)})
    update = {k: v for k, v in USER.items() if k != 'temporary_password'}
    for attack in ATTACKS:
        assert (await http.put(f'{path}/{identifier}', headers=headers, json=update | {field: attack})).status_code == 422
        assert await db.users.find_one({'_id': ObjectId(identifier)}) == before


async def test_admin_role_description_rejects_markup_on_update(env):
    http, db, headers = env
    path = '/api/v1/admin/roles/engineer'
    before = await db.roles.find_one({'name': 'engineer'})
    for attack in ATTACKS:
        assert (await http.put(path, headers=headers, json={'description': attack, 'permissions': before['permissions']})).status_code == 422
        assert await db.roles.find_one({'name': 'engineer'}) == before
    saved = await http.put(path, headers=headers, json={'description': PLAIN, 'permissions': before['permissions']})
    assert saved.status_code == 200
    assert (await db.roles.find_one({'name': 'engineer'}))['description'] == PLAIN
