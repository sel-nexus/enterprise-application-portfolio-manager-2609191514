"""Expose scoped review history and due work."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase
from app.accounts.router import current_session, get_service as get_accounts
from app.accounts.service import AccountService
from app.applications.repository import ApplicationRepository
from app.applications.service import ApplicationService
from app.core.database import get_database
from app.reviews.repository import ReviewRepository
from app.reviews.schemas import AssignmentInput, IntervalInput, ReviewInput
from app.reviews.service import ReviewService

router = APIRouter(prefix='/api/v1/reviews', tags=['reviews'])


def get_service(db: Annotated[AsyncDatabase, Depends(get_database)], accounts: Annotated[AccountService, Depends(get_accounts)]) -> ReviewService:
    """Bind the review service to the shared database."""
    return ReviewService(ReviewRepository(db), accounts, ApplicationService(ApplicationRepository(db), accounts))


@router.get('/due')
async def due(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReviewService, Depends(get_service)], portfolio_id: str = '', standing: Literal['All due', 'No review', 'Overdue'] = 'All due', page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> dict:
    """Return the scoped queue and chart."""
    return await service.queue(session[0], portfolio_id, standing, page, page_size)


@router.put('/interval')
async def interval(data: IntervalInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReviewService, Depends(get_service)]) -> dict:
    """Save an administrator-controlled interval."""
    user = session[0]
    await service.accounts.authorize(user, 'administer')
    await service.repo.set_interval(data.days)
    await service.accounts.repo.audit(user['name'], 'review_interval_change', 'review_interval', f'Changed review interval to {data.days} days.')
    return {'days': data.days}


@router.get('/applications/{application_id}')
async def history(application_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReviewService, Depends(get_service)], page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> dict:
    """Return an application's review history."""
    return await service.history(session[0], application_id, page, page_size)


@router.post('/applications/{application_id}', status_code=201)
async def record(application_id: str, data: ReviewInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReviewService, Depends(get_service)]) -> dict:
    """Record an assessment."""
    return await service.record(session[0], application_id, data)


@router.get('/applications/{application_id}/eligible-reviewers')
async def eligible(application_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReviewService, Depends(get_service)]) -> list[dict]:
    """List eligible reviewers for an editable application."""
    return await service.eligible(session[0], application_id)


@router.put('/applications/{application_id}/assignment')
async def assign(application_id: str, data: AssignmentInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReviewService, Depends(get_service)]) -> dict:
    """Assign or clear a reviewer."""
    return await service.assign(session[0], application_id, data.reviewer_id)
