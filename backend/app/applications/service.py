"""Apply application authorization, validation and audit rules."""

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.accounts.service import AccountService
from app.applications.repository import ApplicationRepository
from app.applications.schemas import ApplicationInput, ApplicationPage, ApplicationResponse


class ApplicationService:
    """Coordinate application inventory operations."""

    def __init__(self, repo: ApplicationRepository, accounts: AccountService) -> None:
        """Bind inventory and authorization services."""
        self.repo, self.accounts = repo, accounts

    async def present(self, doc: dict) -> ApplicationResponse:
        """Convert a stored document into its public representation."""
        portfolio = await self.repo.portfolio(doc['portfolio_id'])
        return ApplicationResponse(id=str(doc['_id']), portfolio_name=portfolio['name'] if portfolio else 'Unknown portfolio', **{k: doc[k] for k in ApplicationInput.model_fields}, lifecycle=doc['lifecycle'])

    async def get(self, user: dict, application_id: str, action: str = 'view') -> dict:
        """Require the requested action on the application's portfolio."""
        await self.accounts.authorize(user, action, resource='application')
        doc = await self.repo.get(application_id)
        if not doc:
            raise HTTPException(status_code=404, detail='Application not found.')
        await self.accounts.authorize(user, action, doc['portfolio_id'], 'application')
        return doc

    async def target(self, user: dict, portfolio_id: str, action: str) -> None:
        """Require access to an existing destination portfolio."""
        await self.accounts.authorize(user, action, portfolio_id, 'application')
        if not await self.repo.portfolio(portfolio_id):
            raise HTTPException(status_code=404, detail='Portfolio not found.')

    async def list(self, user: dict, search: str, portfolio_id: str, criticality: str, lifecycle: str, include_archived: bool, page: int, page_size: int, risk: str = 'All') -> ApplicationPage:
        """List authorized identities with bounded pagination."""
        await self.accounts.authorize(user, 'view', resource='application')
        if portfolio_id:
            await self.accounts.authorize(user, 'view', portfolio_id, 'application')
        docs, total = await self.repo.list(self.accounts.portfolio_scope(user), search, portfolio_id, criticality, lifecycle, include_archived, page, page_size, risk)
        return ApplicationPage(items=[await self.present(doc) for doc in docs], total=total, page=page, page_size=page_size)

    async def create(self, user: dict, data: ApplicationInput) -> ApplicationResponse:
        """Create a unique identity in an authorized portfolio."""
        await self.target(user, data.portfolio_id, 'create')
        fields = data.model_dump() | {'name_key': data.name.casefold(), 'lifecycle': 'Active'}
        try:
            doc = await self.repo.create(fields)
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail='An application with this name already exists.') from exc
        await self.accounts.repo.audit(user['name'], 'create', str(doc['_id']), f'Created application {data.name}.')
        return await self.present(doc)

    async def update(self, user: dict, application_id: str, data: ApplicationInput) -> ApplicationResponse:
        """Update an identity only when both source and destination are editable."""
        previous = await self.get(user, application_id, 'edit')
        await self.target(user, data.portfolio_id, 'edit')
        try:
            doc = await self.repo.update(application_id, data.model_dump() | {'name_key': data.name.casefold()}, previous['portfolio_id'])
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail='An application with this name already exists.') from exc
        if not doc:
            raise HTTPException(status_code=409, detail='Application changed. Reload and try again.')
        await self.accounts.repo.audit(user['name'], 'edit', application_id, f'Edited application {data.name}.')
        return await self.present(doc)

    async def lifecycle(self, user: dict, application_id: str, lifecycle: str) -> ApplicationResponse:
        """Change lifecycle without altering the application's identity."""
        previous = await self.get(user, application_id, 'edit')
        doc = await self.repo.update(application_id, {'lifecycle': lifecycle}, previous['portfolio_id'])
        if not doc:
            raise HTTPException(status_code=409, detail='Application changed. Reload and try again.')
        if previous['lifecycle'] != lifecycle:
            await self.accounts.repo.audit(user['name'], 'lifecycle_change', application_id, f'Changed lifecycle of {doc["name"]} to {lifecycle}.')
        return await self.present(doc)

    async def delete(self, user: dict, application_id: str) -> None:
        """Delete an application and its related reviews and dependencies."""
        doc = await self.get(user, application_id, 'delete')
        if not await self.repo.delete(application_id):
            raise HTTPException(status_code=404, detail='Application not found.')
        await self.accounts.repo.audit(user['name'], 'delete', application_id, f'Deleted application {doc["name"]}.')
