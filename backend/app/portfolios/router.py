"""Expose authenticated portfolio inventory endpoints."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Response
from pymongo.asynchronous.database import AsyncDatabase
from app.accounts.router import current_session, get_service as get_account_service
from app.accounts.service import AccountService
from app.core.database import get_database
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schemas import PortfolioInput, PortfolioPage, PortfolioResponse
from app.portfolios.service import PortfolioService

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])


def get_service(db: Annotated[AsyncDatabase, Depends(get_database)], accounts: Annotated[AccountService, Depends(get_account_service)]) -> PortfolioService:
    """Bind portfolio operations to the shared database and account service."""
    return PortfolioService(PortfolioRepository(db), accounts)


@router.get("", response_model=PortfolioPage)
async def list_portfolios(session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[PortfolioService, Depends(get_service)], search: Annotated[str, Query(max_length=200)] = "", status: Literal["Active", "Archived", "All"] = "Active", page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25) -> PortfolioPage:
    """Search the caller's visible portfolios."""
    return await service.list(session[0], search.strip(), status, page, page_size)


@router.post("", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(data: PortfolioInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[PortfolioService, Depends(get_service)]) -> PortfolioResponse:
    """Create a portfolio."""
    return await service.create(session[0], data)


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(portfolio_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[PortfolioService, Depends(get_service)]) -> PortfolioResponse:
    """Read a visible portfolio."""
    return await service.present(await service.get(session[0], portfolio_id))


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(portfolio_id: str, data: PortfolioInput, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[PortfolioService, Depends(get_service)]) -> PortfolioResponse:
    """Replace editable portfolio fields."""
    return await service.update(session[0], portfolio_id, data)


@router.post("/{portfolio_id}/archive", response_model=PortfolioResponse)
async def archive_portfolio(portfolio_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[PortfolioService, Depends(get_service)]) -> PortfolioResponse:
    """Archive a portfolio."""
    return await service.archive(session[0], portfolio_id)


@router.delete("/{portfolio_id}", status_code=204)
async def delete_portfolio(portfolio_id: str, session: Annotated[tuple[dict, dict], Depends(current_session)], service: Annotated[PortfolioService, Depends(get_service)]) -> Response:
    """Delete an empty portfolio."""
    await service.delete(session[0], portfolio_id)
    return Response(status_code=204)
