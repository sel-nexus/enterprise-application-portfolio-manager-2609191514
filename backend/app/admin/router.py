"""Expose protected administration and audit endpoints."""
from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, Query, Response
from pymongo.asynchronous.database import AsyncDatabase
from app.accounts.router import current_session, get_service as get_accounts
from app.accounts.service import AccountService
from app.admin.repository import AdminRepository
from app.admin.schemas import RoleInput, UserCreate, UserInput
from app.admin.service import AdminService, audit_query
from app.core.database import get_database
from app.reviews.repository import ReviewRepository

router = APIRouter(prefix='/api/v1/admin', tags=['administration'])

def get_service(db: Annotated[AsyncDatabase, Depends(get_database)], accounts: Annotated[AccountService, Depends(get_accounts)]) -> AdminService:
    """Bind the shared database and account service."""
    return AdminService(AdminRepository(db), accounts)

@router.get('/users')
async def users(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)], page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> dict:
    """List people in bounded pages."""
    return await service.list_users(session[0], page, page_size)

@router.post('/users', status_code=201)
async def create_user(data: UserCreate, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)]) -> dict:
    """Create a person with a supplied temporary password."""
    return await service.create_user(session[0], data)

@router.put('/users/{identifier}')
async def update_user(identifier: str, data: UserInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)]) -> dict:
    """Edit a person's role and portfolio assignments."""
    return await service.update_user(session[0], identifier, data)

@router.post('/users/{identifier}/deactivate')
async def deactivate(identifier: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)]) -> dict:
    """Deactivate an account without deleting its history."""
    return await service.deactivate(session[0], identifier)

@router.get('/roles')
async def roles(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)]) -> list[dict]:
    """Return the shipped role settings."""
    return await service.roles(session[0])

@router.put('/roles/{name}')
async def update_role(name: str, data: RoleInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)]) -> dict:
    """Update role restrictions."""
    return await service.update_role(session[0], name, data)

@router.get('/settings')
async def settings(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)]) -> dict:
    """Read the shared review interval."""
    await service.admin(session[0])
    return {'days': await ReviewRepository(service.repo.db).interval()}

@router.get('/audit')
async def audit(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)], who: Annotated[str, Query(max_length=200)] = '', action: Annotated[str, Query(max_length=100)] = '', start: date | None = None, end: date | None = None, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> dict:
    """Return a filtered page of audit events."""
    return await service.audit(session[0], audit_query(who, action, start, end), page, page_size)

@router.get('/audit/export')
async def audit_export(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AdminService, Depends(get_service)], who: Annotated[str, Query(max_length=200)] = '', action: Annotated[str, Query(max_length=100)] = '', start: date | None = None, end: date | None = None) -> Response:
    """Download an authorized, filtered audit CSV."""
    content = await service.export_audit(session[0], audit_query(who, action, start, end))
    return Response(content, media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="audit.csv"', 'Cache-Control': 'no-store'})
