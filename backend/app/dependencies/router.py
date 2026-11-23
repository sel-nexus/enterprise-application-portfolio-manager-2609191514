"""Expose scoped dependency links and summaries."""
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Response
from pymongo.asynchronous.database import AsyncDatabase
from app.accounts.router import current_session, get_service as get_accounts
from app.accounts.service import AccountService
from app.applications.repository import ApplicationRepository
from app.applications.service import ApplicationService
from app.core.database import get_database
from app.dependencies.repository import DependencyRepository
from app.dependencies.schemas import DependencyInput
from app.dependencies.service import DependencyService

router = APIRouter(prefix='/api/v1/dependencies', tags=['dependencies'])


def get_service(db: Annotated[AsyncDatabase, Depends(get_database)], accounts: Annotated[AccountService, Depends(get_accounts)]) -> DependencyService:
    """Bind link and application services to the shared database."""
    return DependencyService(DependencyRepository(db), accounts, ApplicationService(ApplicationRepository(db), accounts))


@router.get('')
async def list_links(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[DependencyService, Depends(get_service)], search: str = '', relationship: Literal['', 'Calls', 'Receives data from', 'Needs at runtime'] = '', portfolio_id: str = '', application_id: str = '', direction: Literal['outgoing', 'incoming'] = 'outgoing', page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> dict:
    """List visible links, chart and unlinked application count."""
    return await service.list(session[0], search, relationship, portfolio_id, application_id, direction, page, page_size)


@router.post('', status_code=201)
async def create_link(data: DependencyInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[DependencyService, Depends(get_service)]) -> dict:
    """Create a directional dependency."""
    return await service.create(session[0], data)


@router.delete('/{link_id}', status_code=204)
async def remove_link(link_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[DependencyService, Depends(get_service)]) -> Response:
    """Remove a link from its editable source."""
    await service.remove(session[0], link_id)
    return Response(status_code=204)
