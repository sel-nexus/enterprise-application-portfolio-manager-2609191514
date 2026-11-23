"""Exercise account routes and authorization against an isolated real MongoDB."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.core.config import settings
from app.core.security import can_access, hash_password
from app.main import app

pytestmark = pytest.mark.asyncio
TEMP = "TemporaryPass123"
NEW = "ChangedPassword123"


@pytest_asyncio.fixture
async def client():
    """Create and remove a uniquely named database for each test."""
    name = "accounts_test_" + uuid4().hex
    mongo = AsyncMongoClient(os.environ.get("MONGODB_TEST_URI", "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=3000, tz_aware=True)
    settings.jwt_secret = "test-only-" + uuid4().hex + uuid4().hex
    db = mongo[name]
    app.state.db = db
    repo = AccountRepository(db)
    await repo.indexes()
    await repo.bootstrap("admin@example.com", "Test Administrator", await hash_password(TEMP))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http, db
    finally:
        await mongo.drop_database(name)
        await mongo.close()


def auth(token):
    """Build the bearer header for a session."""
    return {"Authorization": "Bearer " + token}


async def login(http, password=TEMP, email="admin@example.com"):
    """Submit account credentials."""
    return await http.post("/api/v1/accounts/login", json={"email": email, "password": password})


async def setup(http):
    """Complete first-use setup and return an ordinary access token."""
    response = await login(http)
    assert response.status_code == 200
    initial = response.json()["access_token"]
    response = await http.put("/api/v1/accounts/password", headers=auth(initial), json={"current_password": TEMP, "new_password": NEW, "confirm_password": NEW})
    assert response.status_code == 200
    return response.json()["access_token"], initial


async def test_first_login_password_and_persistent_preferences(client):
    http, db = client
    result = await login(http)
    assert result.status_code == 200 and result.json()["must_change_password"] is True
    initial = result.json()["access_token"]
    assert (await http.get('/api/v1/accounts/me', headers=auth(initial))).status_code == 401
    assert (await http.put('/api/v1/accounts/preferences', headers=auth(initial), json={'landing_page': 'applications'})).status_code == 401
    bad = await http.put('/api/v1/accounts/password', headers=auth(initial), json={'current_password': 'wrong', 'new_password': NEW, 'confirm_password': NEW})
    assert bad.status_code == 400 and bad.json()['detail'] == 'The current password is incorrect.'
    for new, confirm in [('short1', 'short1'), ('abcdefghijkl', 'abcdefghijkl'), ('abcdefghijk1', 'different1234'), ('é' * 72 + '1', 'é' * 72 + '1')]:
        assert (await http.put('/api/v1/accounts/password', headers=auth(initial), json={'current_password': TEMP, 'new_password': new, 'confirm_password': confirm})).status_code == 422
    changed = await http.put('/api/v1/accounts/password', headers=auth(initial), json={'current_password': TEMP, 'new_password': NEW, 'confirm_password': NEW})
    assert changed.status_code == 200 and not changed.json()['must_change_password']
    token = changed.json()['access_token']
    assert (await http.put('/api/v1/accounts/password', headers=auth(initial), json={'current_password': TEMP, 'new_password': NEW, 'confirm_password': NEW})).status_code == 401
    me = await http.get('/api/v1/accounts/me', headers=auth(token))
    assert me.status_code == 200
    assert me.json()['name'] == 'Test Administrator' and me.json()['landing_page'] == 'dashboard'
    assert 'password_hash' not in me.json()
    preference = await http.put('/api/v1/accounts/preferences', headers=auth(token), json={'landing_page': 'reviews_due'})
    assert preference.status_code == 200 and preference.json()['landing_page'] == 'reviews_due'
    assert (await http.put('/api/v1/accounts/preferences', headers=auth(token), json={'landing_page': 'unknown'})).status_code == 422
    assert (await db.users.find_one({'email': 'admin@example.com'}))['landing_page'] == 'reviews_due'
    assert (await login(http, TEMP)).status_code == 401
    assert (await login(http, NEW)).status_code == 200
    assert await db.audit.count_documents({'action': 'sign_in'}) >= 2


async def test_failed_inactive_signin_and_revocation(client):
    http, db = client
    assert (await http.get('/api/v1/accounts/me')).status_code == 401
    assert (await http.get('/api/v1/accounts/me', headers=auth('invalid'))).status_code == 401
    bad_login = await login(http, 'incorrect')
    assert bad_login.status_code == 401 and bad_login.json()['detail'] == 'Email or password is incorrect.'
    assert (await login(http, TEMP, 'nobody@example.com')).status_code == 401
    token, _ = await setup(http)
    assert (await http.post('/api/v1/accounts/logout', headers=auth(token))).status_code == 200
    assert (await http.post('/api/v1/accounts/logout', headers=auth(token))).status_code == 401
    assert (await http.post('/api/v1/accounts/logout', headers=auth('invalid'))).status_code == 401
    assert (await http.post('/api/v1/accounts/logout')).status_code == 401
    assert (await http.get('/api/v1/accounts/me', headers=auth(token))).status_code == 401
    result = await login(http, NEW)
    assert result.status_code == 200
    next_token = result.json()['access_token']
    await db.users.update_one({'email': 'admin@example.com'}, {'$set': {'active': False}})
    assert (await http.get('/api/v1/accounts/me', headers=auth(next_token))).status_code == 401
    assert (await login(http, NEW)).status_code == 401
    assert await db.audit.count_documents({'action': 'failed_sign_in'}) >= 3


async def test_password_rotation_revokes_other_sessions(client):
    http, _ = client
    token, _ = await setup(http)
    result = await login(http, NEW)
    assert result.status_code == 200
    other = result.json()['access_token']
    changed = await http.put('/api/v1/accounts/password', headers=auth(token), json={'current_password': NEW, 'new_password': 'AnotherPassword123', 'confirm_password': 'AnotherPassword123'})
    assert changed.status_code == 200
    assert (await http.get('/api/v1/accounts/me', headers=auth(other))).status_code == 401
    assert (await http.get('/api/v1/accounts/me', headers=auth(changed.json()['access_token']))).status_code == 200


async def test_role_scope_and_restrictions(client):
    _, db = client
    service = AccountService(AccountRepository(db))
    person = {'active': True, 'role': 'engineer', 'portfolio_ids': ['one']}
    assert can_access(person, 'edit', 'one', resource='application')
    assert not can_access(person, 'edit', 'two', resource='application')
    assert not can_access(person, 'edit', 'one', resource='portfolio')
    assert not can_access(person, 'delete', 'one')
    assert not can_access(person, 'audit')
    assert service.portfolio_scope(person) == ['one']
    await service.authorize(person, 'edit', 'one', 'application')
    await db.roles.insert_one({'name': 'engineer', 'permissions': {'edit': False}})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await service.authorize(person, 'edit', 'one', 'application')
    assert exc.value.status_code == 403
    for role in ('administrator', 'executive', 'auditor'):
        assert service.portfolio_scope({'role': role}) is None
    assert not can_access({'active': True, 'role': 'read_only'}, 'export')


async def test_signed_expired_session_and_login_operator_injection(client):
    """A real session with an expired signed token cannot authenticate."""
    from datetime import datetime, timedelta, timezone
    import jwt

    http, db = client
    token, _ = await setup(http)
    claims = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])
    claims['exp'] = datetime.now(timezone.utc) - timedelta(seconds=30)
    expired = jwt.encode(claims, settings.jwt_secret, algorithm='HS256')
    assert (await http.get('/api/v1/accounts/me', headers=auth(token))).status_code == 200
    response = await http.get('/api/v1/accounts/me', headers=auth(expired))
    assert response.status_code == 401
    assert response.json()['detail'] == 'Invalid or expired session.'
    for body in ({'email': {'$ne': None}, 'password': NEW},
                 {'email': 'admin@example.com', 'password': {'$ne': None}}):
        assert (await http.post('/api/v1/accounts/login', json=body)).status_code == 422
    assert await db.users.count_documents({}) == 1


async def test_account_required_fields_and_invalid_types(client):
    http, _ = client
    for body in ({'email': 'admin@example.com'}, {'password': TEMP},
                 {'email': 'admin@example.com', 'password': ''},
                 {'email': 'bad', 'password': TEMP},
                 {'email': 'admin@example.com', 'password': 'x' * 257}):
        assert (await http.post('/api/v1/accounts/login', json=body)).status_code == 422
    result = await login(http)
    assert result.status_code == 200
    initial = result.json()['access_token']
    payload = {'current_password': TEMP, 'new_password': NEW, 'confirm_password': NEW}
    for key in payload:
        assert (await http.put('/api/v1/accounts/password', headers=auth(initial), json={k: v for k, v in payload.items() if k != key})).status_code == 422


async def test_signed_claims_and_session_branches(client):
    """Reject missing or wrong claims and sessions invalidated independently of the JWT."""
    import jwt
    from bson import ObjectId

    http, db = client
    token, setup_token = await setup(http)
    claims = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])
    for key in ('sub', 'jti', 'purpose', 'iat', 'exp'):
        altered = {k: v for k, v in claims.items() if k != key}
        response = await http.get('/api/v1/accounts/me', headers=auth(jwt.encode(altered, settings.jwt_secret, algorithm='HS256')))
        assert response.status_code == 401 and response.json()['detail'] == 'Invalid or expired session.'
    for changes in ({'purpose': 'other'}, {'purpose': 'setup'}, {'sub': str(ObjectId())}, {'jti': uuid4().hex}):
        signed = jwt.encode(claims | changes, settings.jwt_secret, algorithm='HS256')
        assert (await http.get('/api/v1/accounts/me', headers=auth(signed))).status_code == 401
    assert (await http.get('/api/v1/accounts/me', headers=auth(setup_token))).status_code == 401
    await db.users.update_one({'email': 'admin@example.com'}, {'$set': {'must_change_password': True}})
    assert (await http.get('/api/v1/accounts/me', headers=auth(token))).status_code == 401
    await db.users.update_one({'email': 'admin@example.com'}, {'$set': {'must_change_password': False}, '$inc': {'token_version': 1}})
    assert (await http.get('/api/v1/accounts/me', headers=auth(token))).status_code == 401
