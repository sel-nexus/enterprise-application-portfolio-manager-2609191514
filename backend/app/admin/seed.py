"""Populate a fictional, idempotent six-month operating history."""
from datetime import datetime, timedelta, timezone
from pymongo.asynchronous.database import AsyncDatabase
from app.core.security import ROLE_ACTIONS

ACTIONS = ('view', 'create', 'edit', 'delete', 'export', 'administer')
ESTATE = [
    ('Customer Experience', 'Customer services', 'Maya Chen', ['Customer Gateway', 'Account Console', 'Service Desk', 'Journey Planner', 'Feedback Studio', 'Identity Exchange']),
    ('Commerce Platforms', 'Commerce', 'Owen Patel', ['Payments Hub', 'Order Ledger', 'Pricing Engine', 'Checkout Service', 'Merchant Portal', 'Billing Bridge']),
    ('Operations', 'Operations', 'Lena Brooks', ['Dispatch Board', 'Asset Registry', 'Fleet Planner', 'Workforce Scheduler', 'Supply Tracker', 'Field Toolkit']),
    ('Data and Insights', 'Analytics', 'Amir Morgan', ['Insight Warehouse', 'Metrics Catalog', 'Event Stream', 'Forecast Studio', 'Data Exchange', 'Research Workbench']),
    ('Corporate Services', 'Corporate', 'Nora Ellis', ['People Directory', 'Finance Workspace', 'Contract Archive', 'Travel Desk', 'Procurement Center', 'Learning Portal']),
    ('Infrastructure', 'Technology', 'Sofia Lane', ['Cloud Control', 'Service Monitor', 'Access Broker', 'Release Coordinator', 'Network Inventory', 'Legacy Batch']),
]
PEOPLE = [
    ('Maya Chen', 'maya.chen@example.com', 'portfolio_leader', 0, False, 'Nora Ellis', True),
    ('Owen Patel', 'owen.patel@example.com', 'portfolio_leader', 1, False, 'Nora Ellis', True),
    ('Lena Brooks', 'lena.brooks@example.com', 'engineer', 2, False, 'Maya Chen', True),
    ('Amir Morgan', 'amir.morgan@example.com', 'engineer', 3, True, 'Lena Brooks', True),
    ('Nora Ellis', 'nora.ellis@example.com', 'executive', 4, False, '', True),
    ('Sofia Lane', 'sofia.lane@example.com', 'auditor', 5, False, 'Nora Ellis', True),
    ('Riley Park', 'riley.park@example.com', 'read_only', 0, False, 'Maya Chen', True),
    ('Jordan Vale', 'jordan.vale@example.com', 'engineer', 5, False, 'Sofia Lane', False),
]

async def seed_roles(db: AsyncDatabase) -> None:
    """Insert defaults without overwriting administrator edits."""
    for role, actions in ROLE_ACTIONS.items():
        await db.roles.update_one({'name': role}, {'$setOnInsert': {'description': role.replace('_', ' ').title(), 'permissions': {key: key in actions for key in ACTIONS}}}, upsert=True)
    await db.settings.update_one({'_id': 'review_interval'}, {'$setOnInsert': {'days': 90}}, upsert=True)

async def seed_database(db: AsyncDatabase) -> None:
    """Insert fictional estate history without resetting existing records."""
    await seed_roles(db)
    now = datetime.now(timezone.utc)
    portfolios = []
    apps = []
    for group_index, (name, area, owner, names) in enumerate(ESTATE):
        await db.portfolios.update_one({'name_key': name.casefold()}, {'$setOnInsert': {'name': name, 'name_key': name.casefold(), 'owner': owner, 'product_area': area, 'description': f'Responsible for {area.lower()} applications and their operating outcomes.', 'status': 'Active'}}, upsert=True)
        portfolio = await db.portfolios.find_one({'name_key': name.casefold()})
        portfolios.append(str(portfolio['_id']))
        for index, app_name in enumerate(names):
            number = group_index * 6 + index
            lifecycle = 'Retired' if number in (10, 34, 35) else ('Deprecated' if number in (4, 16, 27) else 'Active')
            fields = {'name': app_name, 'name_key': app_name.casefold(), 'description': f'Supports {area.lower()} workflows.', 'portfolio_id': str(portfolio['_id']), 'product_area': area, 'business_owner': owner, 'technology_owner': 'Lena Brooks', 'inventory_owner': owner, 'criticality': ['Low', 'Medium', 'High', 'Critical'][number % 4], 'tier': number % 4 + 1, 'technology_stack': ['Python, MongoDB', 'Java, PostgreSQL', 'TypeScript, Node.js'][number % 3], 'lifecycle': lifecycle}
            await db.applications.update_one({'name_key': app_name.casefold()}, {'$setOnInsert': fields}, upsert=True)
            app = await db.applications.find_one({'name_key': app_name.casefold()})
            apps.append(app)
    for name, email, role, group, vendor, manager, active in PEOPLE:
        # Invalid bcrypt material means these fictional records cannot authenticate.
        fields = {'name': name, 'email': email, 'role': role, 'portfolio_ids': [portfolios[group]], 'vendor_staff': vendor, 'manager': manager, 'active': active, 'password_hash': '!', 'must_change_password': True, 'token_version': 0, 'last_sign_in': None}
        await db.users.update_one({'email': email}, {'$setOnInsert': fields}, upsert=True)
    reviewer = await db.users.find_one({'email': 'lena.brooks@example.com'})
    reviewers = [await db.users.find_one({'email': email}) for email in ('maya.chen@example.com', 'owen.patel@example.com', 'lena.brooks@example.com', 'amir.morgan@example.com')]
    for index, app in enumerate(apps):
        if index in (2, 15, 28): continue
        assigned = reviewers[index // 6] if index // 6 < len(reviewers) else None
        if index % 3 == 0 and assigned and app['portfolio_id'] in assigned.get('portfolio_ids', []):
            await db.applications.update_one({'_id': app['_id'], 'assigned_reviewer_id': {'$exists': False}}, {'$set': {'assigned_reviewer_id': str(assigned['_id']), 'assigned_reviewer_name': assigned['name']}})
        latest_age = 115 if index % 4 == 0 else 25 + index % 20
        for review_index, age in enumerate((latest_age + 150, latest_age + 100, latest_age + 50, latest_age)):
            # Cap history to six months while keeping four distinct assessments.
            age = min(age, 180 - (3 - review_index))
            when = now - timedelta(days=age)
            quality = max(35, min(95, 89 - (index // 6) * 7 + review_index * 2 + index % 4))
            risk = 'High' if index // 6 >= 4 and review_index == 3 else ('Medium' if quality < 75 else 'Low')
            key = f'estate-review:{index}:{review_index}'
            fields = {'seed_key': key, 'application_id': str(app['_id']), 'date': when.date().isoformat(), 'created_at': when, 'recorder_id': str(reviewer['_id']), 'recorder_name': reviewer['name'], 'health': quality - 2, 'quality': quality, 'automation_coverage': quality - 10, 'unit_test_coverage': quality - 6, 'open_defects': 2 + index % 9, 'open_critical_defects': index % 3, 'risk': risk, 'note': ['Coverage improved after the release.', 'Defects remain under active review.', 'Release risk was assessed with the team.', 'Regression coverage is being expanded.'][review_index]}
            await db.reviews.update_one({'seed_key': key}, {'$setOnInsert': fields}, upsert=True)
    for index in range(27):
        source, target = apps[index if index < 24 else index + 3], apps[30 + index % 3]
        relation = ['Calls', 'Receives data from', 'Needs at runtime'][index % 3]
        fields = {'from_application_id': str(source['_id']), 'to_application_id': str(target['_id']), 'relationship': relation, 'note': 'Supports the shared operating workflow.'}
        await db.dependencies.update_one({k: fields[k] for k in ('from_application_id', 'relationship', 'to_application_id')}, {'$setOnInsert': fields}, upsert=True)
    events = [('sign_in', 'Signed in.'), ('create', 'Created an application record.'), ('edit', 'Updated application ownership.'), ('review_recorded', 'Recorded a quality review on Payments Hub.'), ('reviewer_assigned', 'Assigned a reviewer to Operations.'), ('dependency_added', 'Added a dependency to Cloud Control.'), ('dependency_removed', 'Removed an obsolete dependency.'), ('lifecycle_change', 'Changed an application lifecycle.'), ('export', 'Exported a portfolio report.')]
    for index in range(36):
        action, summary = events[index % len(events)]
        key = f'estate-audit:{index}'
        fields = {'seed_key': key, 'when': now - timedelta(days=index * 5), 'who': PEOPLE[index % len(PEOPLE)][0], 'action': action, 'record': str(apps[index]['_id']), 'summary': summary}
        await db.audit.update_one({'seed_key': key}, {'$setOnInsert': fields}, upsert=True)
