"""Expose authenticated application inventory operations."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Response
from pymongo.asynchronous.database import AsyncDatabase
from app.accounts.router import current_session, get_service as get_account_service
from app.accounts.service import AccountService
from app.core.database import get_database
from app.applications.repository import ApplicationRepository
from app.applications.schemas import ApplicationInput, ApplicationPage, ApplicationResponse, LifecycleInput
from app.applications.service import ApplicationService

router = APIRouter(prefix='/api/v1/applications', tags=['applications'])


def get_service(db: Annotated[AsyncDatabase, Depends(get_database)], accounts: Annotated[AccountService, Depends(get_account_service)]) -> ApplicationService:
    """Bind the shared database and account service."""
    return ApplicationService(ApplicationRepository(db), accounts)


@router.get('', response_model=ApplicationPage)
async def list_applications(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ApplicationService, Depends(get_service)], search: Annotated[str, Query(max_length=200)] = '', portfolio_id: Annotated[str, Query(max_length=100)] = '', criticality: Literal['All', 'Low', 'Medium', 'High', 'Critical'] = 'All', lifecycle: Literal['Default', 'All', 'Active', 'Deprecated', 'Retired'] = 'Default', include_archived: bool = False, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> ApplicationPage:
    """Search visible applications."""
    return await service.list(session[0], search.strip(), portfolio_id, criticality, lifecycle, include_archived, page, page_size)


@router.post('', response_model=ApplicationResponse, status_code=201)
async def create_application(data: ApplicationInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ApplicationService, Depends(get_service)]) -> ApplicationResponse:
    """Create an application identity."""
    return await service.create(session[0], data)


@router.get('/{application_id}', response_model=ApplicationResponse)
async def get_application(application_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ApplicationService, Depends(get_service)]) -> ApplicationResponse:
    """Read a visible application."""
    return await service.present(await service.get(session[0], application_id))


@router.put('/{application_id}', response_model=ApplicationResponse)
async def update_application(application_id: str, data: ApplicationInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ApplicationService, Depends(get_service)]) -> ApplicationResponse:
    """Replace editable identity fields."""
    return await service.update(session[0], application_id, data)


@router.put('/{application_id}/lifecycle', response_model=ApplicationResponse)
async def update_lifecycle(application_id: str, data: LifecycleInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ApplicationService, Depends(get_service)]) -> ApplicationResponse:
    """Change lifecycle separately from identity."""
    return await service.lifecycle(session[0], application_id, data.lifecycle)


@router.delete('/{application_id}', status_code=204)
async def delete_application(application_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[ApplicationService, Depends(get_service)]) -> Response:
    """Remove an application and its associated records."""
    await service.delete(session[0], application_id)
    return Response(status_code=204)
