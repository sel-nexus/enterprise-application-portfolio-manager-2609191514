"""Exercise administration and seeded history with real MongoDB."""
import os
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.accounts.repository import AccountRepository
from app.admin.seed import seed_database, seed_roles
from app.core.config import settings
from app.core.security import hash_password
from app.main import app

pytestmark = pytest.mark.asyncio
TEMP = 'TemporaryPassword123'
NEW = 'ChangedPassword123'

def auth(token):
    """Supply a bearer session."""
    return {'Authorization': 'Bearer ' + token}

@pytest_asyncio.fixture
async def client():
    """Use a uniquely named disposable Mongo database."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'admin_test_' + uuid4().hex
    db = mongo[name]
    app.state.db = db
    settings.jwt_secret = 'test-secret-' + uuid4().hex + uuid4().hex
    repo = AccountRepository(db)
    await repo.indexes()
    await seed_roles(db)
    await repo.bootstrap('admin@example.com', 'Admin Person', await hash_password(TEMP))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        try: yield http, db
        finally:
            await mongo.drop_database(name)
            await mongo.close()

async def access(http, email='admin@example.com', password=TEMP):
    """Complete first-use password setup and obtain access."""
    result = await http.post('/api/v1/accounts/login', json={'email': email, 'password': password})
    assert result.status_code == 200
    token = result.json()['access_token']
    if result.json()['must_change_password']:
        changed = await http.put('/api/v1/accounts/password', headers=auth(token), json={'current_password': password, 'new_password': NEW, 'confirm_password': NEW})
        assert changed.status_code == 200
        token = changed.json()['access_token']
    return token

async def test_user_creation_scope_and_deactivation(client):
    """Require a supplied password, persist scope and deny inactive sessions."""
    http, db = client
    token = await access(http)
    p = await db.portfolios.insert_one({'name': 'Service', 'name_key': 'service', 'owner': 'Owner', 'product_area': 'Service', 'description': '', 'status': 'Active'})
    payload = {'name': 'Dana Person', 'email': 'dana@example.com', 'role': 'engineer', 'portfolio_ids': [str(p.inserted_id)], 'vendor_staff': True, 'manager': 'Admin Person', 'temporary_password': TEMP}
    assert (await http.post('/api/v1/admin/users', headers=auth(token), json={k: v for k, v in payload.items() if k != 'temporary_password'})).status_code == 422
    created = await http.post('/api/v1/admin/users', headers=auth(token), json=payload)
    assert created.status_code == 201 and 'password_hash' not in created.json()
    assert (await http.post('/api/v1/admin/users', headers=auth(token), json=payload)).status_code == 409
    engineer = await access(http, 'dana@example.com')
    assert (await http.get('/api/v1/admin/users', headers=auth(engineer))).status_code == 403
    assert (await http.get('/api/v1/portfolios', headers=auth(engineer))).json()['total'] == 1
    identifier = created.json()['id']
    update = {k: v for k, v in payload.items() if k != 'temporary_password'}
    update['portfolio_ids'] = []
    assert (await http.put(f'/api/v1/admin/users/{identifier}', headers=auth(token), json=update)).status_code == 200
    assert (await http.get('/api/v1/portfolios', headers=auth(engineer))).json()['total'] == 0
    assert (await http.post(f'/api/v1/admin/users/{identifier}/deactivate', headers=auth(token))).status_code == 200
    assert (await http.get('/api/v1/accounts/me', headers=auth(engineer))).status_code == 401
    assert (await http.post('/api/v1/accounts/login', json={'email': 'dana@example.com', 'password': NEW})).status_code == 401
    assert (await db.users.find_one({'email': 'dana@example.com'}))['active'] is False

async def test_roles_and_interval_restrict_real_routes(client):
    """Reject permission expansion and propagate changes to review queue."""
    http, db = client
    token = await access(http)
    roles = (await http.get('/api/v1/admin/roles', headers=auth(token))).json()
    assert len(roles) == 6
    engineer = next(r for r in roles if r['name'] == 'engineer')
    engineer['permissions']['delete'] = True
    assert (await http.put('/api/v1/admin/roles/engineer', headers=auth(token), json={'description': 'Engineering', 'permissions': engineer['permissions']})).status_code == 422
    engineer['permissions']['delete'] = False
    engineer['permissions']['create'] = False
    assert (await http.put('/api/v1/admin/roles/engineer', headers=auth(token), json={'description': 'Engineering', 'permissions': engineer['permissions']})).status_code == 200
    assert (await db.roles.find_one({'name': 'engineer'}))['permissions']['create'] is False
    person = {'name': 'Engineer', 'email': 'engineer@example.com', 'role': 'engineer', 'portfolio_ids': [], 'vendor_staff': False, 'manager': '', 'temporary_password': TEMP}
    assert (await http.post('/api/v1/admin/users', headers=auth(token), json=person)).status_code == 201
    engineer_token = await access(http, person['email'])
    denied = await http.post('/api/v1/applications', headers=auth(engineer_token), json={'name': 'Denied', 'portfolio_id': '000000000000000000000000', 'tier': 1})
    assert denied.status_code == 403
    assert (await http.put('/api/v1/reviews/interval', headers=auth(token), json={'days': 29})).status_code == 422
    assert (await http.put('/api/v1/reviews/interval', headers=auth(token), json={'days': 30})).status_code == 200
    assert (await http.get('/api/v1/reviews/due', headers=auth(token))).json()['interval'] == 30
    assert (await http.get('/api/v1/admin/settings', headers=auth(token))).json()['days'] == 30

async def test_audit_authorization_filters_and_csv_safety(client):
    """Limit audit to administrators and auditors and neutralize formulas."""
    http, db = client
    token = await access(http)
    person = {'name': 'Audit Person', 'email': 'audit@example.com', 'role': 'auditor', 'portfolio_ids': [], 'manager': '', 'vendor_staff': False, 'temporary_password': TEMP}
    assert (await http.post('/api/v1/admin/users', headers=auth(token), json=person)).status_code == 201
    auditor = await access(http, person['email'])
    await AccountRepository(db).audit('=danger', 'edit', '+cmd', '@formula')
    listing = await http.get('/api/v1/admin/audit', headers=auth(auditor), params={'who': '=danger', 'action': 'edit'})
    assert listing.status_code == 200 and listing.json()['total'] == 1
    csv = await http.get('/api/v1/admin/audit/export', headers=auth(auditor), params={'who': '=danger'})
    assert csv.status_code == 200 and "'=danger" in csv.text and "'+cmd" in csv.text and "'@formula" in csv.text
    assert (await http.get('/api/v1/admin/users', headers=auth(auditor))).status_code == 403
    assert (await http.get('/api/v1/admin/audit')).status_code == 401

async def test_seed_counts_idempotence_and_reporting(client):
    """Seed coherent history twice without resetting changes or creating credentials."""
    http, db = client
    await seed_database(db)
    counts = {c: await db[c].count_documents({}) for c in ('portfolios', 'applications', 'reviews', 'dependencies', 'users', 'roles', 'audit')}
    assert counts['portfolios'] == 6 and counts['applications'] == 36 and counts['dependencies'] >= 25
    assert counts['roles'] == 6 and counts['reviews'] >= 120 and counts['audit'] >= 36
    active = await db.applications.find({'lifecycle': 'Active'}).to_list(None)
    review_counts = [await db.reviews.count_documents({'application_id': str(app['_id'])}) for app in active]
    assert sum(count == 0 for count in review_counts) >= 2
    assert all(count == 0 or count >= 4 for count in review_counts)
    assert await db.reviews.count_documents({'risk': 'High'}) >= 4
    assert len(await db.dependencies.distinct('relationship')) == 3
    assigned_due = await db.applications.count_documents({'assigned_reviewer_id': {'$exists': True}})
    assert assigned_due >= 3
    await db.settings.update_one({'_id': 'review_interval'}, {'$set': {'days': 60}})
    await seed_database(db)
    assert counts == {c: await db[c].count_documents({}) for c in counts}
    assert (await db.settings.find_one({'_id': 'review_interval'}))['days'] == 60
    assert (await http.post('/api/v1/accounts/login', json={'email': 'lena.brooks@example.com', 'password': TEMP})).status_code == 401
    token = await access(http)
    dashboard = await http.get('/api/v1/reporting/dashboard', headers=auth(token))
    queue = await http.get('/api/v1/reviews/due', headers=auth(token))
    assert dashboard.status_code == 200 and dashboard.json()['applications'] > 30
    assert queue.status_code == 200 and queue.json()['due_count'] > 0
    assert {'No review', 'Overdue'} <= {x['standing'] for x in queue.json()['items']}
