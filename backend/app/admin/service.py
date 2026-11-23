"""Enforce administration authorization and persistence rules."""
import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.accounts.service import AccountService
from app.admin.repository import AdminRepository
from app.admin.schemas import RoleInput, UserCreate, UserInput
from app.core.security import ROLE_ACTIONS, hash_password

ACTIONS = ('view', 'create', 'edit', 'delete', 'export', 'administer')

def public_user(doc: dict) -> dict:
    """Remove credentials and expose the public identifier."""
    return {k: v for k, v in doc.items() if k not in ('_id', 'password_hash', 'token_version', 'must_change_password')} | {'id': str(doc['_id'])}

def audit_query(who: str, action: str, start: date | None, end: date | None) -> dict:
    """Construct exact-match filters and an inclusive UTC date range."""
    if start and end and start > end:
        raise HTTPException(422, 'From date must precede to date.')
    query = {}
    if who: query['who'] = who
    if action: query['action'] = action
    bounds = {}
    if start: bounds['$gte'] = datetime.combine(start, time.min, tzinfo=timezone.utc)
    if end: bounds['$lt'] = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
    if bounds: query['when'] = bounds
    return query

def safe_cell(value: object) -> str:
    """Neutralize spreadsheet formulas while retaining normal text."""
    text = str(value or '')
    return "'" + text if text.startswith(('\t', '\r', '\n')) or text.lstrip().startswith(('=', '+', '-', '@')) else text

class AdminService:
    """Coordinate access, validation, audit and Mongo operations."""
    def __init__(self, repo: AdminRepository, accounts: AccountService) -> None:
        """Bind persistence and authorization collaborators."""
        self.repo, self.accounts = repo, accounts

    async def admin(self, user: dict) -> None:
        """Require the shipped administrator ceiling and stored permission."""
        await self.accounts.authorize(user, 'administer')

    async def list_users(self, user: dict, page: int, size: int) -> dict:
        """Return people without authentication material."""
        await self.admin(user)
        docs, total = await self.repo.users(page, size)
        return {'items': [public_user(d) for d in docs], 'total': total, 'page': page, 'page_size': size}

    async def create_user(self, actor: dict, data: UserCreate) -> dict:
        """Create an account with a required first-use password change."""
        await self.admin(actor)
        if not await self.repo.portfolios_valid(data.portfolio_ids): raise HTTPException(422, 'Unknown portfolio assignment.')
        fields = data.model_dump(exclude={'temporary_password'})
        fields['email'] = str(data.email).lower()
        fields.update(password_hash=await hash_password(data.temporary_password), active=True, must_change_password=True, token_version=0, last_sign_in=None)
        try:
            result = await self.repo.db.users.insert_one(fields)
        except DuplicateKeyError:
            raise HTTPException(409, 'A person with this email already exists.') from None
        await self.accounts.repo.audit(actor['name'], 'create', str(result.inserted_id), f'Created user {fields["name"]}.')
        return public_user(fields | {'_id': result.inserted_id})

    async def update_user(self, actor: dict, identifier: str, data: UserInput) -> dict:
        """Update assignments without changing credential or historical names."""
        await self.admin(actor)
        existing = await self.repo.user(identifier)
        if not existing: raise HTTPException(404, 'Person not found.')
        if not await self.repo.portfolios_valid(data.portfolio_ids): raise HTTPException(422, 'Unknown portfolio assignment.')
        fields = data.model_dump() | {'email': str(data.email).lower()}
        try:
            await self.repo.db.users.update_one({'_id': existing['_id']}, {'$set': fields})
        except DuplicateKeyError:
            raise HTTPException(409, 'A person with this email already exists.') from None
        await self.accounts.repo.audit(actor['name'], 'role_change' if fields['role'] != existing['role'] else 'edit', identifier, f'Updated user {fields["name"]}.')
        return public_user(existing | fields)

    async def deactivate(self, actor: dict, identifier: str) -> dict:
        """Deactivate without deleting user, sessions or historical records."""
        await self.admin(actor)
        person = await self.repo.user(identifier)
        if not person: raise HTTPException(404, 'Person not found.')
        if person['_id'] == actor['_id']: raise HTTPException(409, 'You cannot deactivate your own account.')
        await self.repo.db.users.update_one({'_id': person['_id']}, {'$set': {'active': False}})
        await self.accounts.repo.audit(actor['name'], 'deactivate', identifier, f'Deactivated {person["name"]}.')
        return public_user(person | {'active': False})

    async def roles(self, actor: dict) -> list[dict]:
        """List the six shipped roles."""
        await self.admin(actor)
        docs = await self.repo.db.roles.find({'name': {'$in': list(ROLE_ACTIONS)}}, {'_id': 0}).sort('name', 1).to_list(None)
        return docs

    async def update_role(self, actor: dict, name: str, data: RoleInput) -> dict:
        """Restrict permissions without exceeding the shipped action matrix."""
        await self.admin(actor)
        if name not in ROLE_ACTIONS: raise HTTPException(404, 'Role not found.')
        permissions = data.permissions.model_dump()
        if any(enabled and key not in ROLE_ACTIONS[name] for key, enabled in permissions.items()):
            raise HTTPException(422, 'Permissions cannot exceed the shipped role matrix.')
        await self.repo.db.roles.update_one({'name': name}, {'$set': {'description': data.description, 'permissions': permissions}}, upsert=True)
        await self.accounts.repo.audit(actor['name'], 'permission_change', name, f'Changed permissions for {name}.')
        return {'name': name, 'description': data.description, 'permissions': permissions}

    async def audit(self, actor: dict, query: dict, page: int, size: int) -> dict:
        """Return filtered audit history to administrators or auditors."""
        await self.accounts.authorize(actor, 'audit', resource='audit')
        docs, total = await self.repo.audit_page(query, page, size)
        return {'items': [{k: v for k, v in d.items() if k != '_id'} | {'id': str(d['_id'])} for d in docs], 'total': total, 'page': page, 'page_size': size}

    async def export_audit(self, actor: dict, query: dict) -> str:
        """Export filtered audit records safely and record the export."""
        await self.accounts.authorize(actor, 'audit', resource='audit')
        await self.accounts.authorize(actor, 'export', resource='audit')
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        keys = ('when', 'who', 'action', 'record', 'summary')
        writer.writerow(['When', 'Who', 'Action', 'Record', 'Summary'])
        async for doc in self.repo.db.audit.find(query).sort([('when', -1), ('_id', -1)]):
            writer.writerow([safe_cell(doc.get(key)) for key in keys])
        await self.accounts.repo.audit(actor['name'], 'export', 'audit', 'Exported audit history.')
        return output.getvalue()
