"""Start an isolated API after checking test MongoDB readiness.

Set E2E_EMAIL, E2E_TEMP_PASSWORD and E2E_NEW_PASSWORD per the root README.
MONGODB_TEST_URI selects test MongoDB; E2E_PYTHON selects the interpreter.
Each run creates a fresh, ownership-marked database and prints its name.
A forced kill, crash or MongoDB outage can prevent cleanup; inspect the printed
name and verify ownership before manually removing an orphaned test database.
The default suite inserts a legacy-markup record. The separate seeded suite
instead enables the production startup seeder in the fresh test database.
"""
import os
from pathlib import Path
import secrets
import sys
import re
from pymongo import MongoClient
import uvicorn

from database import manage

required = ('E2E_EMAIL', 'E2E_TEMP_PASSWORD', 'E2E_NEW_PASSWORD')
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise SystemExit('Missing test environment variables: ' + ', '.join(missing))
uri = os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017')
run_id = os.environ.get('E2E_RUN_ID', '')
token = os.environ.get('E2E_DB_TOKEN', '')
if not re.fullmatch(r'[0-9a-f]{32}', run_id) or not re.fullmatch(r'[0-9a-f]{64}', token):
    raise SystemExit('Missing or invalid generated E2E ownership information.')
database_name = 'portfolio_e2e_' + run_id
with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
    client.admin.command('ping')
    if database_name in client.list_database_names():
        raise SystemExit('Refusing to seed an existing database.')
    client[database_name]['_e2e_owner'].insert_one({'_id': 'owner', 'token': token})
print('Playwright test database:', database_name, flush=True)
try:
    seeded_estate = os.environ.get('E2E_SEEDED_ESTATE') == 'true'
    if not seeded_estate:
        with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
            db = client[database_name]
            portfolio_id = str(db.portfolios.insert_one({
                'name': 'zz E2E legacy portfolio', 'name_key': 'zz e2e legacy portfolio',
                'owner': 'E2E owner', 'product_area': 'E2E', 'description': '', 'status': 'Active',
            }).inserted_id)
            db.applications.insert_one({
                'name': 'zz E2E legacy application', 'name_key': 'zz e2e legacy application',
                'description': '<img src=x onerror="window.__legacyPayloadExecuted=true">',
                'portfolio_id': portfolio_id, 'product_area': '', 'business_owner': '',
                'technology_owner': '', 'inventory_owner': '', 'criticality': 'Medium',
                'tier': 1, 'technology_stack': '', 'lifecycle': 'Active',
            })
    os.environ.update(
        MONGODB_URI=uri, MONGODB_DB=database_name,
        JWT_SECRET=secrets.token_urlsafe(48), BOOTSTRAP_EMAIL=os.environ['E2E_EMAIL'],
        BOOTSTRAP_PASSWORD=os.environ['E2E_TEMP_PASSWORD'], BOOTSTRAP_NAME='E2E Administrator',
        SEED_ON_STARTUP='true' if seeded_estate else 'false', CORS_ORIGINS='http://127.0.0.1:5173',
    )
    os.chdir(Path(__file__).resolve().parents[2] / 'backend')
    sys.path.insert(0, os.getcwd())
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
finally:
    # Global teardown normally drops first. On startup failure or graceful stop,
    # this fallback cleans up only if our database still exists and is owned.
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        exists = database_name in client.list_database_names()
    if exists:
        manage('drop')
