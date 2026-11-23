"""Verify effective account permissions against persisted role restrictions."""
from uuid import uuid4
import os

import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.accounts.repository import AccountRepository
from app.admin.seed import seed_roles
from app.core.config import settings
from app.core.security import hash_password
from app.main import app


@pytest.mark.asyncio
async def test_account_permissions_follow_live_roles_and_server_ceiling():
    """Expose effective permissions on account and preferences responses."""
    mongo = AsyncMongoClient(os.environ.get('MONGODB_TEST_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=3000, tz_aware=True)
    name = 'permissions_test_' + uuid4().hex
    db = mongo[name]
    app.state.db = db
    settings.jwt_secret = 'test-secret-' + uuid4().hex + uuid4().hex
    try:
        await seed_roles(db)
        repo = AccountRepository(db)
        await repo.indexes()
        await repo.bootstrap('admin@example.com', 'Admin', await hash_password('TemporaryPassword123'))
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            login = await http.post('/api/v1/accounts/login', json={'email': 'admin@example.com', 'password': 'TemporaryPassword123'})
            assert login.status_code == 200
            setup = login.json()['access_token']
            changed = await http.put('/api/v1/accounts/password', headers={'Authorization': 'Bearer ' + setup}, json={'current_password': 'TemporaryPassword123', 'new_password': 'ChangedPassword123', 'confirm_password': 'ChangedPassword123'})
            assert changed.status_code == 200
            headers = {'Authorization': 'Bearer ' + changed.json()['access_token']}
            initial = await http.get('/api/v1/accounts/me', headers=headers)
            assert initial.status_code == 200
            assert initial.json()['permissions']['edit'] is True
            await db.roles.update_one({'name': 'administrator'}, {'$set': {'permissions.edit': False, 'permissions.export': False}})
            restricted = await http.get('/api/v1/accounts/me', headers=headers)
            assert restricted.status_code == 200
            assert restricted.json()['permissions']['edit'] is False
            assert restricted.json()['permissions']['export'] is False
            assert restricted.json()['permissions']['create'] is True
            preferences = await http.put('/api/v1/accounts/preferences', headers=headers, json={'landing_page': 'applications'})
            assert preferences.status_code == 200
            assert preferences.json()['permissions'] == restricted.json()['permissions']
            assert (await http.get('/api/v1/reporting/applications/export', headers=headers)).status_code == 403
            await db.users.update_one({'email': 'admin@example.com'}, {'$set': {'role': 'read_only'}})
            await db.roles.update_one({'name': 'read_only'}, {'$set': {'permissions.delete': True, 'permissions.export': True}})
            ceiling = await http.get('/api/v1/accounts/me', headers=headers)
            assert ceiling.status_code == 200
            assert ceiling.json()['permissions']['view'] is True
            assert ceiling.json()['permissions']['delete'] is False
            assert ceiling.json()['permissions']['export'] is False
    finally:
        await mongo.drop_database(name)
        await mongo.close()
