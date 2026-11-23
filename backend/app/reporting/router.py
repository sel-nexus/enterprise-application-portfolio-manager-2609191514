"""Expose authenticated dashboard and report endpoints."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Response
from pymongo.asynchronous.database import AsyncDatabase
from app.accounts.router import current_session, get_service as get_accounts
from app.accounts.service import AccountService
from app.core.database import get_database
from app.reporting.repository import ReportingRepository
from app.reporting.schemas import Filters, Page
from app.reporting.service import ReportingService

router = APIRouter(prefix='/api/v1/reporting', tags=['reporting'])


def get_service(db: Annotated[AsyncDatabase, Depends(get_database)], accounts: Annotated[AccountService, Depends(get_accounts)]) -> ReportingService:
    """Bind reporting to the shared database and authorization."""
    return ReportingService(ReportingRepository(db), accounts)


def get_filters(portfolio_id: Annotated[str, Query(max_length=100)] = '', product_area: Annotated[str, Query(max_length=200)] = '', risk: Literal['All', 'Low', 'Medium', 'High', 'No review'] = 'All', search: Annotated[str, Query(max_length=200)] = '', criticality: Literal['All', 'Low', 'Medium', 'High', 'Critical'] = 'All', lifecycle: Literal['Default', 'All', 'Active', 'Deprecated', 'Retired'] = 'Default', include_archived: bool = False) -> Filters:
    """Validate supported inventory filters."""
    return Filters(portfolio_id=portfolio_id, product_area=product_area, risk=risk, search=search, criticality=criticality, lifecycle=lifecycle, include_archived=include_archived)


@router.get('/dashboard')
async def dashboard(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReportingService, Depends(get_service)], filters: Annotated[Filters, Depends(get_filters)]) -> dict:
    """Return scoped dashboard metrics."""
    return await service.dashboard(session[0], filters)


@router.get('/{kind}')
async def report(kind: Literal['applications', 'portfolios'], session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReportingService, Depends(get_service)], filters: Annotated[Filters, Depends(get_filters)], page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> Page:
    """Return a bounded page of scoped report rows."""
    rows = await service.report(session[0], kind, filters)
    return Page(items=rows[(page - 1) * page_size:page * page_size], total=len(rows), page=page, page_size=page_size)


@router.get('/{kind}/export')
async def export(kind: Literal['applications', 'portfolios'], session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ReportingService, Depends(get_service)], filters: Annotated[Filters, Depends(get_filters)]) -> Response:
    """Download an authorized and audited CSV report."""
    content = await service.export(session[0], kind, filters)
    return Response(content=content, media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{kind}.csv"', 'Cache-Control': 'no-store'})
