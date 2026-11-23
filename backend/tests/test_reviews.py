"""Exercise review APIs against a dedicated real Mongo database."""
import os
from datetime import date, timedelta
from uuid import uuid4
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.core.config import settings
from app.main import app
from app.reviews.repository import ReviewRepository

pytestmark = pytest.mark.asyncio
BASE = '/api/v1/reviews'

@pytest_asyncio.fixture
async def env():
    """Create authenticated users and a disposable database."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'reviews_test_' + uuid4().hex
    db = mongo[name]
    settings.jwt_secret = 'test-only-' + uuid4().hex * 2
    app.state.db = db
    repo = AccountRepository(db)
    await repo.indexes()
    await ReviewRepository(db).indexes()
    headers = {}
    users = {}
    for role in ('administrator', 'engineer', 'read_only', 'executive'):
        doc = {'name': role, 'email': role + '@example.com', 'role': role, 'active': True, 'portfolio_ids': [], 'must_change_password': False, 'token_version': 0}
        doc['_id'] = (await db.users.insert_one(doc)).inserted_id
        users[role] = doc
        token = await AccountService(repo).issue(doc, 'access')
        headers[role] = {'Authorization': 'Bearer ' + token.access_token}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, db, headers, users
    finally:
        await mongo.drop_database(name)
        await mongo.close()

async def estate(db, name='Finance', status='Active', lifecycle='Active'):
    """Insert a portfolio and application with string reference."""
    pid = str((await db.portfolios.insert_one({'name': name, 'status': status})).inserted_id)
    aid = str((await db.applications.insert_one({'name': name + ' app', 'portfolio_id': pid, 'lifecycle': lifecycle})).inserted_id)
    return pid, aid

def review(day=None, **changes):
    """Build a valid assessment."""
    return {'date': (day or date.today()).isoformat(), 'health': 0, 'quality': 100, 'automation_coverage': 42, 'unit_test_coverage': 50, 'open_defects': 2, 'open_critical_defects': 1, 'risk': 'High', 'note': 'Checked'} | changes

async def test_validation_history_assignment_and_audit(env):
    http, db, headers, users = env
    pid, aid = await estate(db)
    admin = headers['administrator']
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    path = f'{BASE}/applications/{aid}'
    assert (await http.get(path + '/eligible-reviewers', headers=admin)).status_code == 200
    engineer_id = str(users['engineer']['_id'])
    assert (await http.put(path + '/assignment', headers=admin, json={'reviewer_id': engineer_id})).status_code == 200
    for fields in ({'health': -1}, {'quality': 101}, {'automation_coverage': 101}, {'unit_test_coverage': -1}, {'open_defects': -1}, {'open_critical_defects': 3}, {'open_defects': 1.5}, {'risk': 'Critical'}, {'date': (date.today() + timedelta(days=1)).isoformat()}):
        assert (await http.post(path, headers=admin, json=review(**fields))).status_code == 422
    older = await http.post(path, headers=admin, json=review(date.today() - timedelta(days=100)))
    first = await http.post(path, headers=admin, json=review(quality=10))
    latest = await http.post(path, headers=admin, json=review(quality=20))
    assert older.status_code == first.status_code == latest.status_code == 201
    history_response = await http.get(path, headers=admin)
    assert history_response.status_code == 200
    history = history_response.json()
    assert [x['quality'] for x in history['items']] == [20, 10, 100]
    assert history['assigned_reviewer_id'] == engineer_id
    assert (await db.reviews.find_one({'_id': __import__('bson').ObjectId(latest.json()['id'])}))['application_id'] == aid
    assert (await http.put(path + '/assignment', headers=admin, json={'reviewer_id': str(users['read_only']['_id'])})).status_code == 422
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'active': False}})
    assert (await http.put(path + '/assignment', headers=admin, json={'reviewer_id': engineer_id})).status_code == 422
    history_response = await http.get(path, headers=admin)
    assert history_response.status_code == 200 and history_response.json()['assigned_reviewer_name'] == 'engineer'
    cleared = await http.put(path + '/assignment', headers=admin, json={'reviewer_id': None})
    assert cleared.status_code == 200 and cleared.json() == {'reviewer_id': None, 'reviewer_name': None}
    history_after_clear = await http.get(path, headers=admin)
    assert history_after_clear.status_code == 200
    assert history_after_clear.json()['assigned_reviewer_id'] is None
    assert history_after_clear.json()['assigned_reviewer_name'] is None
    saved = await db.applications.find_one({'_id': __import__('bson').ObjectId(aid)})
    assert saved['assigned_reviewer_id'] is None and saved['assigned_reviewer_name'] is None
    assert await db.audit.count_documents({'action': 'review_recorded', 'record': aid}) == 3
    assert await db.audit.count_documents({'action': 'reviewer_assigned', 'record': aid}) == 2

async def test_recent_review_removes_due_item_without_clearing_assignment(env):
    """Recording a recent review changes standing without losing assignment."""
    http, db, headers, users = env
    pid, aid = await estate(db)
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    admin = headers['administrator']
    reviewer_id = str(users['engineer']['_id'])
    assert (await http.put(f'{BASE}/applications/{aid}/assignment', headers=admin, json={'reviewer_id': reviewer_id})).status_code == 200
    due = await http.get(BASE + '/due', headers=admin)
    assert due.status_code == 200 and due.json()['total'] == 1
    assert (await http.post(f'{BASE}/applications/{aid}', headers=admin, json=review())).status_code == 201
    due = await http.get(BASE + '/due', headers=admin)
    assert due.status_code == 200 and due.json()['total'] == 0
    history = await http.get(f'{BASE}/applications/{aid}', headers=admin)
    assert history.status_code == 200 and history.json()['assigned_reviewer_id'] == reviewer_id
    assert await db.reviews.count_documents({'application_id': aid}) == 1


async def test_due_order_threshold_scope_interval_and_chart(env):
    http, db, headers, users = env
    pid, unreviewed = await estate(db, 'Alpha')
    old = str((await db.applications.insert_one({'name': 'Old', 'portfolio_id': pid, 'lifecycle': 'Deprecated'})).inserted_id)
    current = str((await db.applications.insert_one({'name': 'Current', 'portfolio_id': pid, 'lifecycle': 'Active'})).inserted_id)
    await db.applications.insert_one({'name': 'Retired', 'portfolio_id': pid, 'lifecycle': 'Retired'})
    other_pid, other = await estate(db, 'Other')
    await estate(db, 'Archived', status='Archived')
    admin = headers['administrator']
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    for aid, days in ((old, 91), (current, 90)):
        assert (await http.post(f'{BASE}/applications/{aid}', headers=admin, json=review(date.today() - timedelta(days=days)))).status_code == 201
    queue_response = await http.get(BASE + '/due', headers=headers['engineer'])
    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert [x['application_id'] for x in queue['items']] == [unreviewed, old]
    assert queue['chart'][0]['current'] == 1 and queue['chart'][0]['due'] == 2
    assert queue['interval'] == 90
    assert (await http.get(BASE + '/due', headers=headers['engineer'], params={'portfolio_id': other_pid})).status_code == 403
    assert (await http.get(f'{BASE}/applications/{other}', headers=headers['engineer'])).status_code == 403
    assert (await http.post(f'{BASE}/applications/{old}', headers=headers['read_only'], json=review())).status_code == 403
    assert (await http.put(BASE + '/interval', headers=headers['executive'], json={'days': 100})).status_code == 403
    for days in (29, 366, 30.5):
        assert (await http.put(BASE + '/interval', headers=admin, json={'days': days})).status_code == 422
    assert (await http.put(BASE + '/interval', headers=admin, json={'days': 100})).status_code == 200
    due = await http.get(BASE + '/due', headers=headers['engineer'])
    assert due.status_code == 200 and due.json()['total'] == 1
    overdue = await http.get(BASE + '/due', headers=headers['engineer'], params={'standing': 'Overdue'})
    assert overdue.status_code == 200 and overdue.json()['total'] == 0
    assert (await http.get(BASE + '/due')).status_code == 401
    assert await db.audit.count_documents({'action': 'review_interval_change'}) == 1


async def test_required_review_fields_eligible_and_missing_applications(env):
    http, db, headers, users = env
    pid, aid = await estate(db)
    admin = headers['administrator']
    await db.users.update_one({'_id': users['engineer']['_id']}, {'$set': {'portfolio_ids': [pid]}})
    path = f'{BASE}/applications/{aid}'
    eligible = await http.get(path + '/eligible-reviewers', headers=admin)
    assert eligible.status_code == 200
    assert {item['id'] for item in eligible.json()} == {str(users['administrator']['_id']), str(users['engineer']['_id'])}
    assert (await http.get(path + '/eligible-reviewers', headers=headers['read_only'])).status_code == 403
    assert (await http.get(path + '/eligible-reviewers')).status_code == 401
    for field in ('health', 'quality', 'automation_coverage', 'unit_test_coverage', 'open_defects', 'open_critical_defects', 'risk'):
        assert (await http.post(path, headers=admin, json={k: v for k, v in review().items() if k != field})).status_code == 422
    for patch in ({'health': True}, {'quality': '10'}, {'note': 'x' * 4001}, {'risk': {'$ne': None}}):
        assert (await http.post(path, headers=admin, json=review(**patch))).status_code == 422
    for identifier in ('not-an-object-id', '000000000000000000000000'):
        missing = f'{BASE}/applications/{identifier}'
        assert (await http.get(missing, headers=admin)).status_code == 404
        assert (await http.post(missing, headers=admin, json=review())).status_code == 404
        assert (await http.get(missing + '/eligible-reviewers', headers=admin)).status_code == 404
        assert (await http.put(missing + '/assignment', headers=admin, json={'reviewer_id': None})).status_code == 404
    assert (await http.put(BASE + '/interval', headers=admin, json={})).status_code == 422
    assert await db.reviews.count_documents({}) == 0
