"""Exercise reporting APIs against an isolated real Mongo database."""
import csv
import io
import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/reporting'


@pytest_asyncio.fixture
async def env():
    """Create a disposable database and authenticated users."""
    client = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'reporting_test_' + uuid4().hex
    db = client[name]
    settings.jwt_secret = 'test-only-' + uuid4().hex * 2
    app.state.db = db
    accounts = AccountRepository(db)
    users, headers = {}, {}
    for role in ('administrator', 'engineer', 'read_only'):
        user = {'name': role, 'email': role + '@example.com', 'role': role, 'active': True, 'portfolio_ids': [], 'must_change_password': False, 'token_version': 0}
        user['_id'] = (await db.users.insert_one(user)).inserted_id
        users[role] = user
        token = await AccountService(accounts).issue(user, 'access')
        headers[role] = {'Authorization': 'Bearer ' + token.access_token}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, db, users, headers
    finally:
        await client.drop_database(name)
        await client.close()


async def add_portfolio(db, name, status='Active'):
    """Persist a portfolio and return its public ID."""
    return str((await db.portfolios.insert_one({'name': name, 'owner': 'Owner', 'product_area': 'Finance', 'status': status})).inserted_id)


async def add_app(db, pid, name, lifecycle='Active'):
    """Persist an inventory identity."""
    doc = {'name': name, 'name_key': name.casefold(), 'portfolio_id': pid, 'lifecycle': lifecycle, 'product_area': 'Finance', 'criticality': 'High', 'tier': 1, 'business_owner': 'Owner', 'technology_owner': 'Tech', 'inventory_owner': 'Inventory', 'description': '', 'technology_stack': ''}
    return str((await db.applications.insert_one(doc)).inserted_id)


async def add_review(db, aid, quality, risk='High', days=0, created=0):
    """Persist a review with explicit tie-breaking time."""
    await db.reviews.insert_one({'application_id': aid, 'date': (date.today() - timedelta(days=days)).isoformat(), 'created_at': datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=created), 'quality': quality, 'health': quality, 'automation_coverage': quality, 'unit_test_coverage': 45, 'open_defects': 4, 'open_critical_defects': 2, 'risk': risk})


async def test_dashboard_latest_filters_lifecycle_and_empty(env):
    http, db, users, headers = env
    pid = await add_portfolio(db, 'Finance')
    other = await add_portfolio(db, 'Hidden')
    archived = await add_portfolio(db, 'Archived', 'Archived')
    a = await add_app(db, pid, 'Payments')
    b = await add_app(db, pid, 'Ledger', 'Deprecated')
    await add_app(db, pid, 'Retired', 'Retired')
    await add_app(db, other, 'Secret')
    await add_app(db, archived, 'Archived app')
    await add_review(db, a, 20, days=1)
    await add_review(db, a, 40, created=1)
    await add_review(db, a, 80, created=2)
    await add_review(db, b, 81, risk='Low', days=91)
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    response = await http.get(BASE + '/dashboard', headers=headers['engineer'])
    assert response.status_code == 200
    data = response.json()
    assert (data['quality'], data['health'], data['automation_coverage']) == (81, 81, 81)
    assert (data['applications'], data['portfolios'], data['open_critical_defects'], data['applications_at_risk']) == (2, 1, 4, 1)
    assert data['groups'][0]['reviews_due'] == 1
    filtered = (await http.get(BASE + '/dashboard', headers=headers['engineer'], params={'risk': 'High'})).json()
    assert filtered['quality'] == 80 and filtered['applications'] == 1
    empty = (await http.get(BASE + '/dashboard', headers=headers['engineer'], params={'product_area': 'Elsewhere'})).json()
    assert empty['quality'] is None and empty['applications'] == 0 and empty['groups'] == []
    assert (await http.get(BASE + '/dashboard', headers=headers['engineer'], params={'portfolio_id': other})).status_code == 403
    assert (await http.get(BASE + '/dashboard', headers=headers['engineer'], params={'risk': 'Severe'})).status_code == 422
    assert (await http.get(BASE + '/dashboard')).status_code == 401
    assert (await http.get('/api/v1/applications', headers=headers['engineer'], params={'risk': 'High'})).json()['total'] == 1


async def test_reports_export_scope_and_csv_injection(env):
    http, db, users, headers = env
    pid = await add_portfolio(db, 'Visible')
    hidden = await add_portfolio(db, 'Hidden')
    a = await add_app(db, pid, '=SUM(1,2)')
    b = await add_app(db, pid, 'Visible target', 'Retired')
    secret = await add_app(db, hidden, 'Secret')
    await db.dependencies.insert_many([{'from_application_id': a, 'to_application_id': b}, {'from_application_id': a, 'to_application_id': secret}])
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    await db.users.update_one({'_id': users['read_only']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    params = {'lifecycle': 'All', 'include_archived': 'true'}
    result = (await http.get(BASE + '/applications', headers=headers['engineer'], params=params)).json()
    assert result['total'] == 2
    row = next(x for x in result['items'] if x['id'] == a)
    assert row['depends_on'] == 1 and row['review_standing'] == 'No review'
    response = await http.get(BASE + '/applications/export', headers=headers['engineer'], params=params)
    assert response.status_code == 200
    records = list(csv.DictReader(io.StringIO(response.text)))
    assert len(records) == 2 and records[0]['Name'] == "'=SUM(1,2)"
    assert 'Secret' not in response.text
    assert await db.audit.count_documents({'action': 'export', 'record': 'applications'}) == 1
    assert (await http.get(BASE + '/applications/export', headers=headers['read_only'])).status_code == 403
    assert (await http.get(BASE + '/portfolios', headers=headers['engineer'])).json()['items'][0]['applications'] == 1
    assert (await http.get(BASE + '/portfolios/export', headers=headers['engineer'])).status_code == 200
    assert (await http.get(BASE + '/applications', headers=headers['engineer'], params={'page_size': 101})).status_code == 422
    await db.roles.insert_one({'name': 'engineer', 'permissions': {'view': True, 'export': False}})
    assert (await http.get(BASE + '/portfolios/export', headers=headers['engineer'])).status_code == 403


async def test_empty_report_and_filtered_export(env):
    http, db, users, headers = env
    admin = headers['administrator']
    assert (await http.get(BASE + '/portfolios', headers=admin)).json()['total'] == 0
    assert (await http.get(BASE + '/dashboard', headers=admin)).json()['quality'] is None
    pid = await add_portfolio(db, 'Finance')
    a = await add_app(db, pid, 'One')
    await add_app(db, pid, 'Two')
    await add_review(db, a, 75, risk='High')
    response = await http.get(BASE + '/applications/export', headers=admin, params={'risk': 'High', 'search': 'One'})
    assert len(list(csv.DictReader(io.StringIO(response.text)))) == 1
