"""Enforce authorization and coordinate directional dependencies."""
from collections import Counter
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.accounts.service import AccountService
from app.applications.service import ApplicationService
from app.dependencies.repository import DependencyRepository
from app.dependencies.schemas import DependencyInput


class DependencyService:
    """Apply visibility, edit and audit rules to links."""
    def __init__(self, repo: DependencyRepository, accounts: AccountService, applications: ApplicationService) -> None:
        """Bind persistence and shared authorization services."""
        self.repo, self.accounts, self.applications = repo, accounts, applications

    async def create(self, user: dict, data: DependencyInput) -> dict:
        """Create a unique non-self link after checking both endpoints."""
        source = await self.applications.get(user, data.from_application_id, 'view')
        await self.applications.get(user, data.from_application_id, 'edit')
        target = await self.applications.get(user, data.to_application_id, 'view')
        source_id, target_id = str(source['_id']), str(target['_id'])
        if source_id == target_id:
            raise HTTPException(status_code=422, detail='An application cannot depend on itself.')
        fields = data.model_dump() | {'from_application_id': source_id, 'to_application_id': target_id}
        try:
            doc = await self.repo.create(fields)
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail='That dependency is already recorded.') from exc
        await self.accounts.repo.audit(user['name'], 'dependency_added', str(doc['_id']), f'Added dependency from {source["name"]} to {target["name"]}.')
        return {'id': str(doc['_id']), **fields}

    async def remove(self, user: dict, link_id: str) -> None:
        """Remove a visible link only when its source is editable."""
        await self.accounts.authorize(user, 'view', resource='application')
        doc = await self.repo.get(link_id)
        if not doc:
            raise HTTPException(status_code=404, detail='Dependency not found.')
        source = await self.applications.get(user, doc['from_application_id'], 'view')
        await self.applications.get(user, doc['from_application_id'], 'edit')
        target = await self.applications.get(user, doc['to_application_id'], 'view')
        if not await self.repo.delete(link_id):
            raise HTTPException(status_code=404, detail='Dependency not found.')
        await self.accounts.repo.audit(user['name'], 'dependency_removed', link_id, f'Removed dependency from {source["name"]} to {target["name"]}.')

    async def list(self, user: dict, search: str, relationship: str, portfolio_id: str, application_id: str, direction: str, page: int, page_size: int) -> dict:
        """Return a filtered page and summary within the visible estate."""
        await self.accounts.authorize(user, 'view', resource='application')
        if portfolio_id:
            await self.accounts.authorize(user, 'view', portfolio_id, 'application')
        if application_id:
            application = await self.applications.get(user, application_id, 'view')
            application_id = str(application['_id'])
        apps = await self.repo.visible_applications(self.accounts.portfolio_scope(user))
        names = {str(app['_id']): app for app in apps}
        ids = list(names)
        portfolio_names = await self.repo.portfolios(list({app['portfolio_id'] for app in apps}))
        target_ids = [key for key, app in names.items() if app['portfolio_id'] == portfolio_id] if portfolio_id else None
        docs, total = await self.repo.list_links(ids, search, relationship, target_ids, application_id, direction, page, page_size, names)
        items = []
        for doc in docs:
            source, target = names[doc['from_application_id']], names[doc['to_application_id']]
            items.append({'id': str(doc['_id']), 'from_application_id': doc['from_application_id'], 'from_name': source['name'], 'from_portfolio_id': source['portfolio_id'], 'relationship': doc['relationship'], 'to_application_id': doc['to_application_id'], 'to_name': target['name'], 'note': doc.get('note', ''), 'portfolio_id': target['portfolio_id'], 'portfolio_name': portfolio_names.get(target['portfolio_id'], 'Unknown portfolio')})
        links = await self.repo.links_for_summary(ids)
        incoming = Counter(link['to_application_id'] for link in links)
        linked = {link[key] for link in links for key in ('from_application_id', 'to_application_id')}
        chart = [{'application_id': key, 'application_name': names[key]['name'], 'count': count} for key, count in incoming.items()]
        chart.sort(key=lambda row: (-row['count'], row['application_name'].casefold(), row['application_id']))
        unlinked = sum(1 for key, app in names.items() if app.get('lifecycle') in ('Active', 'Deprecated') and key not in linked)
        portfolios = [{'id': key, 'name': value} for key, value in sorted(portfolio_names.items(), key=lambda row: row[1].casefold())]
        return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'chart': chart[:8], 'unlinked_count': unlinked, 'portfolios': portfolios}
