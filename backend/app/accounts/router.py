"""Expose the account API and reusable authentication dependencies."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.accounts.repository import AccountRepository
from app.accounts.schemas import AccountResponse, LoginRequest, Message, PasswordChange, Preferences, TokenResponse
from app.accounts.service import AccountService
from app.core.database import get_database

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])
bearer = HTTPBearer(auto_error=False)


def get_service(db: Annotated[AsyncDatabase, Depends(get_database)]) -> AccountService:
    """Create a service backed by the shared database."""
    return AccountService(AccountRepository(db))


async def current_session(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], service: Annotated[AccountService, Depends(get_service)]) -> tuple[dict, dict]:
    """Require a normal active bearer session."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    return await service.authenticate(credentials.credentials)


async def password_session(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], service: Annotated[AccountService, Depends(get_service)]) -> tuple[dict, dict]:
    """Allow an initial setup token only for password replacement."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return await service.authenticate(credentials.credentials, allow_setup=True)


@router.post("/login", response_model=TokenResponse, summary="Sign in")
async def login(data: LoginRequest, service: Annotated[AccountService, Depends(get_service)]) -> TokenResponse:
    """Authenticate credentials and issue a session."""
    return await service.login(data)


@router.get("/me", response_model=AccountResponse, summary="Read account")
async def me(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AccountService, Depends(get_service)]) -> AccountResponse:
    """Return the authenticated person's account."""
    return await service.account(session[0])


@router.put("/password", response_model=TokenResponse, summary="Change password")
async def password(data: PasswordChange, session: Annotated[tuple[dict, dict], Depends(password_session)], service: Annotated[AccountService, Depends(get_service)]) -> TokenResponse:
    """Replace the password and rotate the session."""
    return await service.change_password(session[0], data)


@router.put("/preferences", response_model=AccountResponse, summary="Save preferences")
async def preferences(data: Preferences, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AccountService, Depends(get_service)]) -> AccountResponse:
    """Save the account landing choice."""
    return await service.set_landing(session[0], data.landing_page)


@router.post("/logout", response_model=Message, summary="Sign out")
async def logout(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[AccountService, Depends(get_service)]) -> Message:
    """Revoke the active session."""
    await service.repo.revoke(session[1]["jti"])
    return Message(message="Signed out.")
