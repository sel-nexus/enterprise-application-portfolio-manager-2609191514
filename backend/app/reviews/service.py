"""Apply review authorization and due-standing rules."""
from datetime import date
from fastapi import HTTPException
from app.accounts.service import AccountService
from app.applications.service import ApplicationService
from app.core.security import can_access
from app.reviews.repository import ReviewRepository
from app.reviews.schemas import ReviewInput


def present(doc: dict) -> dict:
    """Expose review fields without BSON identifiers."""
    return {**{k: v for k, v in doc.items() if k != '_id'}, 'id': str(doc['_id'])}


class ReviewService:
    """Coordinate assessments, assignments and the due queue."""
    def __init__(self, repo: ReviewRepository, accounts: AccountService, applications: ApplicationService) -> None:
        """Bind collaborators."""
        self.repo, self.accounts, self.applications = repo, accounts, applications

    async def record(self, user: dict, application_id: str, data: ReviewInput) -> dict:
        """Record a review without changing the assignment."""
        app = await self.applications.get(user, application_id, 'create')
        fields = data.model_dump() | {'date': data.date.isoformat(), 'application_id': application_id, 'recorder_id': str(user['_id']), 'recorder_name': user['name']}
        doc = await self.repo.create(fields)
        await self.accounts.repo.audit(user['name'], 'review_recorded', application_id, f'Recorded a quality review on {app["name"]}.')
        return present(doc)

    async def history(self, user: dict, application_id: str, page: int, page_size: int) -> dict:
        """Return scoped history and assignment."""
        app = await self.applications.get(user, application_id)
        docs, total = await self.repo.history(application_id, page, page_size)
        return {'items': [present(x) for x in docs], 'total': total, 'page': page, 'page_size': page_size, 'assigned_reviewer_id': app.get('assigned_reviewer_id'), 'assigned_reviewer_name': app.get('assigned_reviewer_name'), 'interval': await self.repo.interval()}

    async def eligible(self, user: dict, application_id: str) -> list[dict]:
        """Return active users with review permission on the portfolio."""
        app = await self.applications.get(user, application_id, 'edit')
        result = []
        for candidate in await self.repo.eligible_users():
            role = await self.repo.db.roles.find_one({'name': candidate['role']})
            permissions = role.get('permissions') if role else None
            if can_access(candidate, 'create', app['portfolio_id'], permissions, 'application'):
                result.append({'id': str(candidate['_id']), 'name': candidate['name']})
        return result

    async def assign(self, user: dict, application_id: str, reviewer_id: str | None) -> dict:
        """Assign only an eligible active reviewer, or clear the assignment."""
        app = await self.applications.get(user, application_id, 'edit')
        reviewer = None
        if reviewer_id:
            eligible = await self.eligible(user, application_id)
            if reviewer_id not in [x['id'] for x in eligible]:
                raise HTTPException(status_code=422, detail='Reviewer is not eligible for this portfolio.')
            reviewer = await self.accounts.repo.by_id(reviewer_id)
        updated = await self.repo.assign(application_id, app['portfolio_id'], reviewer)
        if not updated:
            raise HTTPException(status_code=409, detail='Application changed. Reload and try again.')
        await self.accounts.repo.audit(user['name'], 'reviewer_assigned', application_id, f'Assigned reviewer on {app["name"]}.' if reviewer else f'Cleared reviewer on {app["name"]}.')
        return {'reviewer_id': updated.get('assigned_reviewer_id'), 'reviewer_name': updated.get('assigned_reviewer_name')}

    async def queue(self, user: dict, portfolio_id: str, standing: str, page: int, page_size: int) -> dict:
        """Calculate due work and current/due counts from latest reviews."""
        await self.accounts.authorize(user, 'view', resource='application')
        if portfolio_id:
            await self.accounts.authorize(user, 'view', portfolio_id, 'application')
        interval = await self.repo.interval()
        rows, chart = [], []
        today = date.today()
        for portfolio in await self.repo.estate(self.accounts.portfolio_scope(user), portfolio_id):
            counts = {'portfolio_id': str(portfolio['_id']), 'portfolio_name': portfolio['name'], 'current': 0, 'due': 0}
            for app in portfolio['applications']:
                history, _ = await self.repo.history(str(app['_id']), 1, 1)
                latest = history[0] if history else None
                age = (today - date.fromisoformat(latest['date'])).days if latest else None
                status = 'No review' if latest is None else ('Overdue' if age > interval else 'Current')
                counts['current' if status == 'Current' else 'due'] += 1
                if status != 'Current' and (standing == 'All due' or standing == status):
                    rows.append({'application_id': str(app['_id']), 'application_name': app['name'], 'portfolio_id': str(portfolio['_id']), 'portfolio_name': portfolio['name'], 'last_review': latest['date'] if latest else None, 'days_since_review': age, 'assigned_reviewer_id': app.get('assigned_reviewer_id'), 'assigned_reviewer_name': app.get('assigned_reviewer_name'), 'risk': latest['risk'] if latest else None, 'standing': status})
            chart.append(counts)
        rows.sort(key=lambda x: (x['last_review'] is not None, x['last_review'] or '', x['application_name'].casefold(), x['application_id']))
        chart.sort(key=lambda x: (-x['due'], x['portfolio_name'].casefold(), x['portfolio_id']))
        return {'items': rows[(page - 1) * page_size:page * page_size], 'total': len(rows), 'page': page, 'page_size': page_size, 'interval': interval, 'due_count': sum(x['due'] for x in chart), 'chart': chart}
