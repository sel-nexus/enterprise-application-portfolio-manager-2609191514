"""Exercise cross-feature HTTP journeys with an isolated real MongoDB."""
import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.admin.seed import seed_roles
from app.applications.repository import ApplicationRepository
from app.core.config import settings
from app.dependencies.repository import DependencyRepository
from app.main import app
from app.portfolios.repository import PortfolioRepository
from app.reviews.repository import ReviewRepository

pytestmark = pytest.mark.asyncio
API = '/api/v1'


@pytest_asyncio.fixture
async def env():
    """Provision the production indexes and a unique, disposable Mongo database."""
    uri = os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017')
    name = 'integration_test_' + uuid4().hex
    missing = object()
    previous_db = getattr(app.state, 'db', missing)
    previous_secret = settings.jwt_secret
    mongo = AsyncMongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        db = mongo[name]
        settings.jwt_secret = 'test-only-' + uuid4().hex * 2
        app.state.db = db
        accounts = AccountRepository(db)
        for repo in (accounts, PortfolioRepository(db), ApplicationRepository(db), ReviewRepository(db), DependencyRepository(db)):
            await repo.indexes()
        await seed_roles(db)
        admin = {'name': 'Integration Admin', 'email': 'admin@example.com', 'role': 'administrator', 'active': True, 'portfolio_ids': [], 'must_change_password': False, 'token_version': 0}
        admin['_id'] = (await db.users.insert_one(admin)).inserted_id
        token = await AccountService(accounts).issue(admin, 'access')
        headers = {'Authorization': 'Bearer ' + token.access_token}
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            yield http, db, headers, uri
    finally:
        try:
            await mongo.drop_database(name)
        finally:
            try:
                await mongo.close()
            finally:
                try:
                    settings.jwt_secret = previous_secret
                finally:
                    if previous_db is missing:
                        if hasattr(app.state, 'db'):
                            del app.state.db
                    else:
                        app.state.db = previous_db


async def create_portfolio(http, headers, name='Finance'):
    response = await http.post(API + '/portfolios', headers=headers, json={'name': name, 'owner': 'Morgan', 'product_area': 'Finance'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def identity(pid, name='Payments', owner='Alex'):
    return {'name': name, 'portfolio_id': pid, 'product_area': 'Finance', 'business_owner': owner, 'technology_owner': 'Sam', 'inventory_owner': 'Lee', 'criticality': 'High', 'tier': 1}


async def create_application(http, headers, pid, name='Payments'):
    response = await http.post(API + '/applications', headers=headers, json=identity(pid, name))
    assert response.status_code == 201, response.text
    return response.json()['id']


def review(days=0, quality=76, risk='High'):
    return {'date': (date.today() - timedelta(days=days)).isoformat(), 'health': 64, 'quality': quality, 'automation_coverage': 55, 'unit_test_coverage': 49, 'open_defects': 7, 'open_critical_defects': 3, 'risk': risk, 'note': 'Reviewed'}


async def report_row(http, headers, kind, identifier):
    response = await http.get(API + '/reporting/' + kind, headers=headers)
    assert response.status_code == 200, response.text
    return next(row for row in response.json()['items'] if row['id'] == identifier)


async def test_new_review_updates_inventory_history_portfolio_and_both_reports(env):
    http, db, admin, _ = env
    pid = await create_portfolio(http, admin)
    aid = await create_application(http, admin, pid)
    other = await create_application(http, admin, pid, 'Ledger')
    path = f'{API}/reviews/applications/{aid}'
    assert (await http.post(path, headers=admin, json=review(days=30, quality=20, risk='Low'))).status_code == 201
    assert (await http.post(f'{API}/reviews/applications/{other}', headers=admin, json=review(days=20, quality=40, risk='Low') | {'health': 40, 'open_critical_defects': 1})).status_code == 201
    assert (await report_row(http, admin, 'portfolios', pid))['quality'] == 30

    updated = review(quality=90, risk='High') | {'health': 80, 'automation_coverage': 70, 'unit_test_coverage': 65, 'open_defects': 9, 'open_critical_defects': 4}
    response = await http.post(path, headers=admin, json=updated)
    assert response.status_code == 201, response.text
    review_id = response.json()['id']

    # Inventory and portfolio identities are separate from the review history
    # consumed by those screens; risk filtering must use the latest review.
    listing = await http.get(API + '/applications', headers=admin, params={'risk': 'High'})
    assert listing.status_code == 200
    assert [item['id'] for item in listing.json()['items']] == [aid]
    response = await http.get(f'{API}/applications/{aid}', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['id'] == aid
    response = await http.get(f'{API}/portfolios/{pid}', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['application_count'] == 2
    portfolio_apps = await http.get(API + '/applications', headers=admin, params={'portfolio_id': pid, 'lifecycle': 'All', 'include_archived': 'true'})
    assert portfolio_apps.status_code == 200
    assert {item['id'] for item in portfolio_apps.json()['items']} == {aid, other}
    history_response = await http.get(path, headers=admin)
    assert history_response.status_code == 200
    latest = history_response.json()['items'][0]
    assert latest['id'] == review_id
    assert {key: latest[key] for key in updated} == updated

    app_report = await report_row(http, admin, 'applications', aid)
    keys = ('health', 'quality', 'automation_coverage', 'unit_test_coverage', 'open_defects', 'open_critical_defects', 'risk')
    assert {key: app_report[key] for key in keys} == {key: updated[key] for key in keys}
    portfolio_report = await report_row(http, admin, 'portfolios', pid)
    assert (portfolio_report['quality'], portfolio_report['health'], portfolio_report['open_critical_defects'], portfolio_report['applications_at_risk']) == (65, 60, 5, 1)
    assert (await db.reviews.find_one({'_id': ObjectId(review_id)}))['quality'] == 90

    # Rejecting an invalid write leaves all downstream values unchanged.
    invalid = await http.post(path, headers=admin, json=updated | {'open_critical_defects': 10})
    assert invalid.status_code == 422
    response = await http.get(path, headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['id'] == review_id
    assert (await report_row(http, admin, 'applications', aid))['quality'] == 90
    assert (await report_row(http, admin, 'portfolios', pid))['quality'] == 65
    assert await db.reviews.count_documents({'application_id': aid}) == 2


async def test_review_assignment_and_latest_values_flow_across_surfaces(env):
    http, db, admin, uri = env
    pid = await create_portfolio(http, admin)
    aid = await create_application(http, admin, pid)
    user = {'name': 'Riley Reviewer', 'email': 'riley@example.com', 'role': 'engineer', 'portfolio_ids': [pid], 'temporary_password': 'TemporaryPass123'}
    created_user = await http.post(API + '/admin/users', headers=admin, json=user)
    assert created_user.status_code == 201
    reviewer = created_user.json()['id']
    path = f'{API}/reviews/applications/{aid}'
    assigned = await http.put(path + '/assignment', headers=admin, json={'reviewer_id': reviewer})
    assert assigned.status_code == 200
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    due = response.json()
    assert due['items'][0]['assigned_reviewer_id'] == reviewer
    assert due['items'][0]['assigned_reviewer_name'] == 'Riley Reviewer'
    assert (await report_row(http, admin, 'applications', aid))['assigned_reviewer'] == 'Riley Reviewer'
    assert (await http.post(path, headers=admin, json=review(days=100, quality=20, risk='Low'))).status_code == 201
    latest = await http.post(path, headers=admin, json=review())
    assert latest.status_code == 201
    # An older review entered later must not replace the latest figures.
    assert (await http.post(path, headers=admin, json=review(days=30, quality=5))).status_code == 201
    response = await http.get(path, headers=admin)
    assert response.status_code == 200, response.text
    history = response.json()
    assert history['items'][0]['id'] == latest.json()['id']
    assert history['assigned_reviewer_id'] == reviewer
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    response = await http.get(API + '/reporting/dashboard', headers=admin)
    assert response.status_code == 200, response.text
    dashboard = response.json()
    assert (dashboard['applications'], dashboard['quality'], dashboard['health'], dashboard['automation_coverage'], dashboard['open_critical_defects'], dashboard['applications_at_risk']) == (1, 76, 64, 55, 3, 1)
    application = await report_row(http, admin, 'applications', aid)
    assert (application['quality'], application['risk'], application['review_standing'], application['assigned_reviewer']) == (76, 'High', 'Current', 'Riley Reviewer')
    portfolio = await report_row(http, admin, 'portfolios', pid)
    assert (portfolio['quality'], portfolio['health'], portfolio['open_critical_defects'], portfolio['applications_at_risk'], portfolio['reviews_due']) == (76, 64, 3, 1, 0)
    response = await http.get(API + '/applications', headers=admin, params={'risk': 'High'})
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['id'] == aid
    assert await db.reviews.count_documents({'application_id': aid}) == 3
    assert (await db.applications.find_one({'_id': ObjectId(aid)}))['assigned_reviewer_id'] == reviewer
    assert await db.audit.count_documents({'record': aid, 'action': 'review_recorded'}) == 3
    # A separate Mongo client observes the persisted state, not process-local state.
    other = AsyncMongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        assert await other[db.name].reviews.count_documents({'application_id': aid}) == 3
    finally:
        await other.close()


async def test_dependency_direction_report_chart_and_removal(env):
    http, db, admin, _ = env
    pid = await create_portfolio(http, admin)
    source = await create_application(http, admin, pid, 'Caller')
    target = await create_application(http, admin, pid, 'Service')
    payload = {'from_application_id': source, 'to_application_id': target, 'relationship': 'Calls', 'note': 'API'}
    created = await http.post(API + '/dependencies', headers=admin, json=payload)
    assert created.status_code == 201
    link = created.json()['id']
    response = await http.get(API + '/dependencies', headers=admin, params={'application_id': source, 'direction': 'outgoing'})
    assert response.status_code == 200, response.text
    outgoing = response.json()
    response = await http.get(API + '/dependencies', headers=admin, params={'application_id': target, 'direction': 'incoming'})
    assert response.status_code == 200, response.text
    incoming = response.json()
    assert outgoing['items'][0]['id'] == incoming['items'][0]['id'] == link
    assert outgoing['items'][0]['to_application_id'] == target
    assert incoming['items'][0]['from_application_id'] == source
    assert outgoing['chart'][0]['application_id'] == target and outgoing['chart'][0]['count'] == 1
    assert (await report_row(http, admin, 'applications', source))['depends_on'] == 1
    assert (await report_row(http, admin, 'applications', target))['depends_on'] == 0
    assert (await http.post(API + '/dependencies', headers=admin, json=payload)).status_code == 409
    assert await db.dependencies.count_documents({}) == 1
    assert (await http.delete(f'{API}/dependencies/{link}', headers=admin)).status_code == 204
    for aid, direction in ((source, 'outgoing'), (target, 'incoming')):
        response = await http.get(API + '/dependencies', headers=admin, params={'application_id': aid, 'direction': direction})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['total'] == 0 and result['chart'] == []
    assert (await report_row(http, admin, 'applications', source))['depends_on'] == 0
    assert await db.dependencies.count_documents({}) == 0


async def test_interval_recalculates_queue_and_portfolio_report_without_changing_reviews(env):
    http, db, admin, _ = env
    pid = await create_portfolio(http, admin)
    aid = await create_application(http, admin, pid)
    assert (await http.post(f'{API}/reviews/applications/{aid}', headers=admin, json=review(days=60))).status_code == 201
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    assert (await report_row(http, admin, 'portfolios', pid))['reviews_due'] == 0
    assert (await http.put(API + '/reviews/interval', headers=admin, json={'days': 30})).status_code == 200
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    queue = response.json()
    assert queue['interval'] == 30 and queue['items'][0]['application_id'] == aid and queue['items'][0]['standing'] == 'Overdue'
    assert (await report_row(http, admin, 'portfolios', pid))['reviews_due'] == 1
    assert (await report_row(http, admin, 'applications', aid))['review_standing'] == 'Overdue'
    assert (await db.settings.find_one({'_id': 'review_interval'}))['days'] == 30
    assert await db.reviews.count_documents({'application_id': aid}) == 1
    assert (await http.put(API + '/reviews/interval', headers=admin, json={'days': 90})).status_code == 200
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    assert (await report_row(http, admin, 'portfolios', pid))['reviews_due'] == 0


async def test_identity_lifecycle_archive_and_delete_cleanup(env):
    http, db, admin, _ = env
    pid = await create_portfolio(http, admin)
    aid = await create_application(http, admin, pid)
    other = await create_application(http, admin, pid, 'Ledger')
    changed = identity(pid, 'Renamed Payments', 'Jordan')
    assert (await http.put(f'{API}/applications/{aid}', headers=admin, json=changed)).status_code == 200
    response = await http.get(f'{API}/applications/{aid}', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['business_owner'] == 'Jordan'
    response = await http.get(API + '/applications', headers=admin, params={'search': 'Renamed'})
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['id'] == aid
    row = await report_row(http, admin, 'applications', aid)
    assert (row['name'], row['business_owner']) == ('Renamed Payments', 'Jordan')
    assert (await http.post(f'{API}/reviews/applications/{aid}', headers=admin, json=review(days=100))).status_code == 201
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    assert aid in [item['application_id'] for item in response.json()['items']]
    for start, end in ((aid, other), (other, aid)):
        assert (await http.post(API + '/dependencies', headers=admin, json={'from_application_id': start, 'to_application_id': end, 'relationship': 'Calls'})).status_code == 201
    assert (await http.put(f'{API}/applications/{aid}/lifecycle', headers=admin, json={'lifecycle': 'Retired'})).status_code == 200
    response = await http.get(API + '/applications', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 1
    response = await http.get(API + '/reporting/dashboard', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['applications'] == 1
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    assert all(x['application_id'] != aid for x in response.json()['items'])
    response = await http.get(API + '/dependencies', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 2
    assert (await http.post(f'{API}/portfolios/{pid}/archive', headers=admin)).status_code == 200
    response = await http.get(API + '/applications', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    response = await http.get(API + '/reporting/dashboard', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['applications'] == 0
    response = await http.get(API + '/reviews/due', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    response = await http.get(API + '/applications', headers=admin, params={'lifecycle': 'All', 'include_archived': 'true'})
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 2
    assert (await http.delete(f'{API}/portfolios/{pid}', headers=admin)).status_code == 409
    assert (await http.delete(f'{API}/applications/{aid}', headers=admin)).status_code == 204
    assert (await http.get(f'{API}/reviews/applications/{aid}', headers=admin)).status_code == 404
    assert await db.applications.find_one({'_id': ObjectId(aid)}) is None
    assert await db.reviews.count_documents({'application_id': aid}) == 0
    assert await db.dependencies.count_documents({'$or': [{'from_application_id': aid}, {'to_application_id': aid}]}) == 0
    response = await http.get(API + '/dependencies', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0
    assert await db.audit.count_documents({'record': aid, 'action': 'delete'}) == 1
    assert (await http.delete(f'{API}/applications/{other}', headers=admin)).status_code == 204
    assert (await http.delete(f'{API}/portfolios/{pid}', headers=admin)).status_code == 204


async def test_failed_cross_feature_writes_preserve_state_and_scope(env):
    http, db, admin, _ = env
    visible = await create_portfolio(http, admin, 'Visible')
    hidden = await create_portfolio(http, admin, 'Hidden')
    aid = await create_application(http, admin, visible, 'Visible app')
    secret = await create_application(http, admin, hidden, 'Hidden app')
    user = {'name': 'Scoped Engineer', 'email': 'engineer@example.com', 'role': 'engineer', 'portfolio_ids': [visible], 'temporary_password': 'TemporaryPass123'}
    created = await http.post(API + '/admin/users', headers=admin, json=user)
    assert created.status_code == 201
    login = await http.post(API + '/accounts/login', json={'email': user['email'], 'password': user['temporary_password']})
    assert login.status_code == 200
    setup = {'Authorization': 'Bearer ' + login.json()['access_token']}
    change = await http.put(API + '/accounts/password', headers=setup, json={'current_password': user['temporary_password'], 'new_password': 'ChangedPassword123', 'confirm_password': 'ChangedPassword123'})
    assert change.status_code == 200
    engineer = {'Authorization': 'Bearer ' + change.json()['access_token']}
    assert (await http.post(f'{API}/reviews/applications/{secret}', headers=engineer, json=review())).status_code == 403
    assert (await http.post(f'{API}/reviews/applications/missing', headers=admin, json=review())).status_code == 404
    assert (await http.post(f'{API}/reviews/applications/{aid}', headers=engineer, json=review() | {'open_critical_defects': 99})).status_code == 422
    payload = {'from_application_id': aid, 'to_application_id': secret, 'relationship': 'Calls'}
    assert (await http.post(API + '/dependencies', headers=engineer, json=payload)).status_code == 403
    assert (await http.post(API + '/dependencies', headers=admin, json=payload | {'to_application_id': 'missing'})).status_code == 404
    assert (await http.put(f'{API}/reviews/applications/{aid}/assignment', headers=admin, json={'reviewer_id': 'missing'})).status_code == 422
    assert await db.reviews.count_documents({}) == 0
    assert await db.dependencies.count_documents({}) == 0
    assert not (await db.applications.find_one({'_id': ObjectId(aid)})).get('assigned_reviewer_id')
    response = await http.get(API + '/reporting/applications', headers=engineer)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 1
    assert (await http.get(API + '/reporting/dashboard', headers=engineer, params={'portfolio_id': hidden})).status_code == 403
    response = await http.get(API + '/reviews/due', headers=engineer)
    assert response.status_code == 200, response.text
    assert response.json()['items'][0]['application_id'] == aid
    response = await http.get(API + '/dependencies', headers=engineer)
    assert response.status_code == 200, response.text
    assert response.json()['total'] == 0


async def test_portfolio_edit_and_deactivation_propagate(env):
    http, db, admin, _ = env
    pid = await create_portfolio(http, admin)
    aid = await create_application(http, admin, pid)
    person = {'name': 'Review Person', 'email': 'reviewer@example.com', 'role': 'engineer', 'portfolio_ids': [pid], 'temporary_password': 'TemporaryPass123'}
    created = await http.post(API + '/admin/users', headers=admin, json=person)
    assert created.status_code == 201
    uid = created.json()['id']
    login = await http.post(API + '/accounts/login', json={'email': person['email'], 'password': person['temporary_password']})
    assert login.status_code == 200
    setup = {'Authorization': 'Bearer ' + login.json()['access_token']}
    changed = await http.put(API + '/accounts/password', headers=setup, json={'current_password': person['temporary_password'], 'new_password': 'ChangedPassword123', 'confirm_password': 'ChangedPassword123'})
    assert changed.status_code == 200
    reviewer = {'Authorization': 'Bearer ' + changed.json()['access_token']}
    assert (await http.put(f'{API}/reviews/applications/{aid}/assignment', headers=admin, json={'reviewer_id': uid})).status_code == 200
    recorded = await http.post(f'{API}/reviews/applications/{aid}', headers=reviewer, json=review(days=100))
    assert recorded.status_code == 201
    edited = await http.put(f'{API}/portfolios/{pid}', headers=admin, json={'name': 'Renamed Finance', 'owner': 'Taylor', 'product_area': 'Finance'})
    assert edited.status_code == 200
    listing = await http.get(API + '/portfolios', headers=admin, params={'search': 'Taylor'})
    assert listing.status_code == 200
    assert listing.json()['items'][0]['id'] == pid
    response = await http.get(f'{API}/applications/{aid}', headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()['portfolio_name'] == 'Renamed Finance'
    row = await report_row(http, admin, 'portfolios', pid)
    assert (row['name'], row['owner']) == ('Renamed Finance', 'Taylor')
    response = await http.get(API + '/reporting/dashboard', headers=admin, params={'portfolio_id': pid})
    assert response.status_code == 200, response.text
    assert response.json()['applications'] == 1
    assert (await http.post(f'{API}/admin/users/{uid}/deactivate', headers=admin)).status_code == 200
    response = await http.get(API + '/admin/users', headers=admin)
    assert response.status_code == 200, response.text
    users = response.json()['items']
    assert next(item for item in users if item['id'] == uid)['active'] is False
    assert (await http.post(API + '/accounts/login', json={'email': person['email'], 'password': 'ChangedPassword123'})).status_code == 401
    assert (await http.get(API + '/reviews/due', headers=reviewer)).status_code == 401
    response = await http.get(f'{API}/reviews/applications/{aid}', headers=admin)
    assert response.status_code == 200, response.text
    history = response.json()
    assert history['items'][0]['recorder_name'] == 'Review Person'
    assert history['assigned_reviewer_name'] == 'Review Person'
    assert (await report_row(http, admin, 'applications', aid))['assigned_reviewer'] == 'Review Person'
    assert (await db.users.find_one({'_id': ObjectId(uid)}))['active'] is False
    assert await db.audit.count_documents({'record': uid, 'action': 'deactivate'}) == 1
