"""Exercise business services directly against isolated real MongoDB."""
import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from bson import ObjectId
from fastapi import HTTPException
from pymongo import AsyncMongoClient

from app.accounts.repository import AccountRepository
from app.accounts.schemas import PasswordChange
from app.accounts.service import AccountService
from app.admin.repository import AdminRepository
from app.admin.schemas import RoleInput, UserCreate, UserInput
from app.admin.seed import seed_roles
from app.admin.service import AdminService, audit_query, safe_cell
from app.applications.repository import ApplicationRepository
from app.applications.schemas import ApplicationInput
from app.applications.service import ApplicationService
from app.dependencies.repository import DependencyRepository
from app.dependencies.schemas import DependencyInput
from app.dependencies.service import DependencyService
from app.core.security import hash_password, verify_password
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schemas import PortfolioInput
from app.portfolios.service import PortfolioService
from app.reporting.repository import ReportingRepository
from app.reporting.schemas import Filters
from app.reporting.service import ReportingService, average
from app.reviews.repository import ReviewRepository
from app.reviews.schemas import ReviewInput
from app.reviews.service import ReviewService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def services():
    """Use a uniquely named database with actual repository implementations."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'service_test_' + uuid4().hex
    db = mongo[name]
    accounts = AccountService(AccountRepository(db))
    portfolios = PortfolioService(PortfolioRepository(db), accounts)
    applications = ApplicationService(ApplicationRepository(db), accounts)
    reviews = ReviewService(ReviewRepository(db), accounts, applications)
    dependencies = DependencyService(DependencyRepository(db), accounts, applications)
    reporting = ReportingService(ReportingRepository(db), accounts)
    admin = AdminService(AdminRepository(db), accounts)
    await accounts.repo.indexes()
    await portfolios.repo.indexes()
    await applications.repo.indexes()
    await dependencies.repo.indexes()
    await seed_roles(db)
    actor = {'name': 'Admin', 'email': 'admin@example.com', 'role': 'administrator', 'active': True, 'portfolio_ids': []}
    actor['_id'] = (await db.users.insert_one(actor.copy())).inserted_id
    try:
        yield db, actor, portfolios, applications, reviews, dependencies, reporting, admin
    finally:
        await mongo.drop_database(name)
        await mongo.close()


async def test_inventory_service_duplicates_scope_and_lifecycle(services):
    db, actor, portfolios, applications, _, _, _, _ = services
    p = await portfolios.create(actor, PortfolioInput(name='Finance', owner='Ada', product_area='Payments'))
    assert (await portfolios.list(actor, '', 'Active', 1, 25)).total == 1
    updated = await portfolios.update(actor, p.id, PortfolioInput(name='Finance', owner='Grace', product_area='Payments'))
    assert updated.owner == 'Grace'
    assert (await db.portfolios.find_one({'name_key': 'finance'}))['owner'] == 'Grace'
    with pytest.raises(HTTPException) as duplicate:
        await portfolios.create(actor, PortfolioInput(name='finance', owner='Other', product_area='Payments'))
    assert duplicate.value.status_code == 409
    data = ApplicationInput(name='Ledger', portfolio_id=p.id, tier=1)
    a = await applications.create(actor, data)
    assert (await applications.get(actor, a.id))['name'] == 'Ledger'
    with pytest.raises(HTTPException) as duplicate_app:
        await applications.create(actor, data)
    assert duplicate_app.value.status_code == 409
    with pytest.raises(HTTPException) as blocked:
        await portfolios.delete(actor, p.id)
    assert blocked.value.status_code == 409
    await applications.lifecycle(actor, a.id, 'Retired')
    await applications.lifecycle(actor, a.id, 'Retired')
    assert await db.audit.count_documents({'record': a.id, 'action': 'lifecycle_change'}) == 1
    assert (await applications.list(actor, '', '', 'All', 'Default', False, 1, 25)).total == 0
    await applications.delete(actor, a.id)
    await portfolios.delete(actor, p.id)
    with pytest.raises(HTTPException) as missing:
        await portfolios.get(actor, p.id)
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as missing_target:
        await applications.create(actor, data)
    assert missing_target.value.status_code == 404


async def test_portfolio_update_returns_404_if_deleted_after_lookup(services):
    db, actor, portfolios, _, _, _, _, _ = services
    target = await portfolios.create(actor, PortfolioInput(name='Target', owner='Owner', product_area='Area'))
    other = await portfolios.create(actor, PortfolioInput(name='Other', owner='Owner', product_area='Area'))
    target_before = await db.portfolios.find_one({'_id': ObjectId(target.id)})
    other_before = await db.portfolios.find_one({'_id': ObjectId(other.id)})
    audits_before = await db.audit.find({}).sort('_id', 1).to_list(None)
    snapshots = []

    class DeletingPortfolioService(PortfolioService):
        async def get(self, user, portfolio_id, action='view'):
            snapshot = await super().get(user, portfolio_id, action)
            snapshots.append(snapshot)
            deleted = await self.repo.db.portfolios.delete_one({'_id': ObjectId(portfolio_id)})
            assert deleted.deleted_count == 1
            return snapshot

    service = DeletingPortfolioService(PortfolioRepository(db), portfolios.accounts)
    with pytest.raises(HTTPException) as missing:
        await service.update(actor, target.id, PortfolioInput(name='Changed', owner='Changed', product_area='Area', status='Archived'))
    assert missing.value.status_code == 404
    assert missing.value.detail == 'Portfolio not found.'
    assert snapshots == [target_before]
    assert await db.portfolios.find_one({'_id': ObjectId(target.id)}) is None
    assert await db.portfolios.find_one({'_id': ObjectId(other.id)}) == other_before
    assert await db.portfolios.count_documents({}) == 1
    assert await db.audit.find({}).sort('_id', 1).to_list(None) == audits_before


async def test_portfolio_delete_returns_404_if_deleted_after_empty_check(services):
    db, actor, portfolios, applications, _, _, _, _ = services
    target = await portfolios.create(actor, PortfolioInput(name='Target', owner='Owner', product_area='Area'))
    other = await portfolios.create(actor, PortfolioInput(name='Other', owner='Owner', product_area='Area'))
    await applications.create(actor, ApplicationInput(name='Other app', portfolio_id=other.id, tier=1))
    await db.users.update_one({'_id': actor['_id']}, {'$set': {'portfolio_ids': [target.id, other.id]}})
    target_before = await db.portfolios.find_one({'_id': ObjectId(target.id)})
    portfolios_before = await db.portfolios.find({'_id': {'$ne': ObjectId(target.id)}}).sort('_id', 1).to_list(None)
    users_before = await db.users.find({}).sort('_id', 1).to_list(None)
    applications_before = await db.applications.find({}).sort('_id', 1).to_list(None)
    audits_before = await db.audit.find({}).sort('_id', 1).to_list(None)
    checked_counts = []
    deleted_snapshots = []

    class RacingPortfolioRepository(PortfolioRepository):
        async def application_count(self, portfolio_id):
            count = await super().application_count(portfolio_id)
            checked_counts.append((portfolio_id, count))
            return count

        async def delete(self, portfolio_id):
            assert checked_counts == [(target.id, 0)]
            deleted_snapshots.append(await self.db.portfolios.find_one({'_id': ObjectId(portfolio_id)}))
            competing_delete = await self.db.portfolios.delete_one({'_id': ObjectId(portfolio_id)})
            assert competing_delete.deleted_count == 1
            return await super().delete(portfolio_id)

    service = PortfolioService(RacingPortfolioRepository(db), portfolios.accounts)
    with pytest.raises(HTTPException) as missing:
        await service.delete(actor, target.id)
    assert missing.value.status_code == 404
    assert missing.value.detail == 'Portfolio not found.'
    assert deleted_snapshots == [target_before]
    assert await db.portfolios.find_one({'_id': ObjectId(target.id)}) is None
    assert await db.portfolios.find({}).sort('_id', 1).to_list(None) == portfolios_before
    assert await db.users.find({}).sort('_id', 1).to_list(None) == users_before
    assert await db.applications.find({}).sort('_id', 1).to_list(None) == applications_before
    assert await db.audit.find({}).sort('_id', 1).to_list(None) == audits_before


async def test_review_and_dependency_service_state_transitions(services):
    db, actor, portfolios, applications, reviews, dependencies, _, _ = services
    p = await portfolios.create(actor, PortfolioInput(name='Portfolio', owner='Owner', product_area='Area'))
    one = await applications.create(actor, ApplicationInput(name='One', portfolio_id=p.id, tier=1))
    two = await applications.create(actor, ApplicationInput(name='Two', portfolio_id=p.id, tier=2))
    assert (await reviews.queue(actor, '', 'All due', 1, 25))['total'] == 2
    assessment = ReviewInput(date=date.today() - timedelta(days=91), health=90, quality=80, automation_coverage=70, unit_test_coverage=60, open_defects=2, open_critical_defects=1, risk='High')
    recorded = await reviews.record(actor, one.id, assessment)
    assert recorded['application_id'] == one.id
    assert (await reviews.history(actor, one.id, 1, 25))['total'] == 1
    assert (await reviews.queue(actor, '', 'Overdue', 1, 25))['total'] == 1
    assert str(actor['_id']) in {u['id'] for u in await reviews.eligible(actor, one.id)}
    assigned = await reviews.assign(actor, one.id, str(actor['_id']))
    assert assigned['reviewer_id'] == str(actor['_id'])
    saved = await db.applications.find_one({'_id': ObjectId(one.id)})
    assert saved['assigned_reviewer_id'] == str(actor['_id'])
    assert saved['assigned_reviewer_name'] == actor['name']
    with pytest.raises(HTTPException) as invalid:
        await reviews.assign(actor, one.id, 'invalid')
    assert invalid.value.status_code == 422
    assert (await reviews.assign(actor, one.id, None))['reviewer_id'] is None
    saved = await db.applications.find_one({'_id': ObjectId(one.id)})
    assert saved['assigned_reviewer_id'] is None and saved['assigned_reviewer_name'] is None
    link = DependencyInput(from_application_id=one.id, to_application_id=two.id, relationship='Calls')
    created = await dependencies.create(actor, link)
    assert (await dependencies.list(actor, '', '', '', '', 'outgoing', 1, 25))['total'] == 1
    with pytest.raises(HTTPException) as duplicate:
        await dependencies.create(actor, link)
    assert duplicate.value.status_code == 409
    with pytest.raises(HTTPException) as self_link:
        await dependencies.create(actor, DependencyInput(from_application_id=one.id, to_application_id=one.id, relationship='Calls'))
    assert self_link.value.status_code == 422
    await dependencies.remove(actor, created['id'])
    assert await db.dependencies.count_documents({}) == 0
    with pytest.raises(HTTPException) as missing:
        await dependencies.remove(actor, created['id'])
    assert missing.value.status_code == 404


async def test_stale_password_change_conflicts_without_new_write(services):
    db, actor, _, _, _, _, _, _ = services
    service = AccountService(AccountRepository(db))
    original_hash = await hash_password('OriginalPassword123')
    await db.users.update_one({'_id': actor['_id']}, {'$set': {'password_hash': original_hash, 'token_version': 0, 'must_change_password': True}})
    stale = await db.users.find_one({'_id': actor['_id']})
    winning_hash = await hash_password('WinningPassword123')
    assert await service.repo.change_password(stale, winning_hash)
    before = await db.users.find_one({'_id': actor['_id']})
    audit_before = await db.audit.count_documents({})
    sessions_before = await db.sessions.count_documents({})
    data = PasswordChange(current_password='OriginalPassword123', new_password='LosingPassword123', confirm_password='LosingPassword123')
    with pytest.raises(HTTPException) as conflict:
        await service.change_password(stale, data)
    assert conflict.value.status_code == 409
    assert conflict.value.detail == 'Account changed. Sign in again.'
    assert await db.users.find_one({'_id': actor['_id']}) == before
    assert await verify_password('WinningPassword123', before['password_hash'])
    assert not await verify_password('LosingPassword123', before['password_hash'])
    assert await db.audit.count_documents({}) == audit_before
    assert await db.sessions.count_documents({}) == sessions_before


async def test_assignment_conflicts_when_application_moves_after_authorization(services):
    db, actor, portfolios, applications, _, _, _, _ = services
    source = await portfolios.create(actor, PortfolioInput(name='Source', owner='Owner', product_area='Area'))
    destination = await portfolios.create(actor, PortfolioInput(name='Destination', owner='Owner', product_area='Area'))
    app = await applications.create(actor, ApplicationInput(name='Service', portfolio_id=source.id, tier=1))
    await db.applications.update_one({'_id': ObjectId(app.id)}, {'$set': {'assigned_reviewer_id': str(actor['_id']), 'assigned_reviewer_name': actor['name']}})
    after_move = []

    class MovingApplicationService(ApplicationService):
        async def get(self, user, application_id, action='view'):
            snapshot = await super().get(user, application_id, action)
            await self.repo.db.applications.update_one({'_id': ObjectId(application_id)}, {'$set': {'portfolio_id': destination.id}})
            after_move.append(await self.repo.db.applications.find_one({'_id': ObjectId(application_id)}))
            return snapshot

    real_accounts = AccountService(AccountRepository(db))
    moving = MovingApplicationService(ApplicationRepository(db), real_accounts)
    service = ReviewService(ReviewRepository(db), real_accounts, moving)
    before_audits = await db.audit.count_documents({'record': app.id, 'action': 'reviewer_assigned'})
    with pytest.raises(HTTPException) as conflict:
        await service.assign(actor, app.id, None)
    assert conflict.value.status_code == 409
    assert conflict.value.detail == 'Application changed. Reload and try again.'
    saved = await db.applications.find_one({'_id': ObjectId(app.id)})
    assert len(after_move) == 1 and saved == after_move[0]
    assert saved['portfolio_id'] == destination.id
    assert saved['assigned_reviewer_id'] == str(actor['_id'])
    assert saved['assigned_reviewer_name'] == actor['name']
    assert await db.audit.count_documents({'record': app.id, 'action': 'reviewer_assigned'}) == before_audits


async def test_admin_service_validations_and_audit_filters(services):
    db, actor, portfolios, _, _, _, _, admin = services
    p = await portfolios.create(actor, PortfolioInput(name='Portfolio', owner='Owner', product_area='Area'))
    data = UserCreate(name='Engineer', email='eng@example.com', role='engineer', portfolio_ids=[p.id], temporary_password='TemporaryPass123')
    person = await admin.create_user(actor, data)
    assert 'password_hash' not in person
    with pytest.raises(HTTPException) as duplicate:
        await admin.create_user(actor, data)
    assert duplicate.value.status_code == 409
    changed = await admin.update_user(actor, person['id'], UserInput(name='Engineer', email='eng@example.com', role='read_only'))
    assert changed['role'] == 'read_only'
    saved = await db.users.find_one({'_id': ObjectId(person['id'])})
    assert saved['role'] == 'read_only' and saved['portfolio_ids'] == []
    assert (await admin.deactivate(actor, person['id']))['active'] is False
    saved = await db.users.find_one({'_id': ObjectId(person['id'])})
    assert saved['active'] is False and saved['role'] == 'read_only'
    with pytest.raises(HTTPException) as self_deactivate:
        await admin.deactivate(actor, str(actor['_id']))
    assert self_deactivate.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        await admin.update_user(actor, 'bad', UserInput(name='X', email='x@example.com', role='engineer'))
    assert missing.value.status_code == 404
    role = next(r for r in await admin.roles(actor) if r['name'] == 'engineer')
    role['permissions']['delete'] = True
    with pytest.raises(HTTPException) as expansion:
        await admin.update_role(actor, 'engineer', RoleInput(description='No expansion', permissions=role['permissions']))
    assert expansion.value.status_code == 422
    with pytest.raises(HTTPException) as dates:
        audit_query('', '', date(2025, 2, 1), date(2025, 1, 1))
    assert dates.value.status_code == 422
    assert safe_cell(' =1+1') == "' =1+1" and safe_cell('ordinary') == 'ordinary'
    assert (await admin.audit(actor, audit_query('', 'deactivate', None, None), 1, 25))['total'] == 1
    assert 'Engineer' in await admin.export_audit(actor, audit_query('', 'deactivate', None, None))


async def test_admin_update_user_rejects_unknown_portfolio_and_duplicate_email_without_writes(services):
    db, actor, portfolios, _, _, _, _, admin = services
    portfolio = await portfolios.create(actor, PortfolioInput(name='Portfolio', owner='Owner', product_area='Area'))
    person = await admin.create_user(actor, UserCreate(name='Engineer', email='eng@example.com', role='engineer', portfolio_ids=[portfolio.id], temporary_password='TemporaryPass123'))
    other = await admin.create_user(actor, UserCreate(name='Other', email='other@example.com', role='engineer', temporary_password='TemporaryPass123'))
    original = await db.users.find_one({'_id': ObjectId(person['id'])})
    other_before = await db.users.find_one({'_id': ObjectId(other['id'])})
    audit_before = await db.audit.count_documents({})
    with pytest.raises(HTTPException) as invalid:
        await admin.update_user(actor, person['id'], UserInput(name='Changed', email='eng@example.com', role='read_only', portfolio_ids=[str(ObjectId())]))
    assert invalid.value.status_code == 422
    assert invalid.value.detail == 'Unknown portfolio assignment.'
    assert await db.users.find_one({'_id': ObjectId(person['id'])}) == original
    assert await db.users.find_one({'_id': ObjectId(other['id'])}) == other_before
    assert await db.audit.count_documents({}) == audit_before
    with pytest.raises(HTTPException) as duplicate:
        await admin.update_user(actor, person['id'], UserInput(name='Changed', email='OTHER@example.com', role='read_only', portfolio_ids=[portfolio.id]))
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail == 'A person with this email already exists.'
    assert await db.users.find_one({'_id': ObjectId(person['id'])}) == original
    assert await db.users.find_one({'_id': ObjectId(other['id'])}) == other_before
    assert await db.audit.count_documents({}) == audit_before


async def test_reporting_service_filters_rounding_and_authorization(services):
    db, actor, portfolios, applications, reviews, _, reporting, _ = services
    p = await portfolios.create(actor, PortfolioInput(name='Portfolio', owner='Owner', product_area='Area'))
    one = await applications.create(actor, ApplicationInput(name='One', portfolio_id=p.id, tier=1, product_area='Area'))
    two = await applications.create(actor, ApplicationInput(name='Two', portfolio_id=p.id, tier=1, product_area='Area'))
    for app, quality in ((one, 50), (two, 51)):
        await reviews.record(actor, app.id, ReviewInput(health=quality, quality=quality, automation_coverage=quality, unit_test_coverage=0, open_defects=0, open_critical_defects=0, risk='Low'))
    dashboard = await reporting.dashboard(actor, Filters())
    assert dashboard['applications'] == 2 and dashboard['quality'] == 51
    assert average([], 'quality') is None
    assert [r['name'] for r in await reporting.report(actor, 'applications', Filters(search='one'))] == ['One']
    assert len(await reporting.report(actor, 'portfolios', Filters())) == 1
    assert 'One' in await reporting.export(actor, 'applications', Filters(search='One'))
    reader = {'name': 'Reader', 'role': 'read_only', 'active': True, 'portfolio_ids': [p.id]}
    with pytest.raises(HTTPException) as denied:
        await reporting.export(reader, 'applications', Filters())
    assert denied.value.status_code == 403
    assert await db.audit.count_documents({'action': 'export', 'record': 'applications'}) == 1
