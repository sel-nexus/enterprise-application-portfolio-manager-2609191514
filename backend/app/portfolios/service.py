"""Apply portfolio authorization, validation, and audit rules."""

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.accounts.service import AccountService
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schemas import PortfolioInput, PortfolioPage, PortfolioResponse


class PortfolioService:
    """Coordinate scoped portfolio operations."""

    def __init__(self, repo: PortfolioRepository, accounts: AccountService) -> None:
        """Bind inventory and account services."""
        self.repo, self.accounts = repo, accounts

    async def present(self, document: dict) -> PortfolioResponse:
        """Build a public view with an actual application count."""
        portfolio_id = str(document["_id"])
        return PortfolioResponse(id=portfolio_id, application_count=await self.repo.application_count(portfolio_id), **{key: document[key] for key in ("name", "owner", "product_area", "description", "status")})

    async def list(self, user: dict, search: str, status: str, page: int, page_size: int) -> PortfolioPage:
        """List the caller's permitted portfolios."""
        await self.accounts.authorize(user, "view", resource="portfolio")
        docs, total = await self.repo.list(self.accounts.portfolio_scope(user), search, status, page, page_size)
        return PortfolioPage(items=[await self.present(doc) for doc in docs], total=total, page=page, page_size=page_size)

    async def get(self, user: dict, portfolio_id: str, action: str = "view") -> dict:
        """Require scope and return an existing document."""
        await self.accounts.authorize(user, action, portfolio_id, "portfolio")
        document = await self.repo.get(portfolio_id)
        if not document:
            raise HTTPException(status_code=404, detail="Portfolio not found.")
        return document

    async def create(self, user: dict, data: PortfolioInput) -> PortfolioResponse:
        """Create a uniquely named portfolio and assign a leader."""
        await self.accounts.authorize(user, "create", resource="portfolio")
        fields = data.model_dump()
        fields["name_key"] = data.name.casefold()
        try:
            document = await self.repo.create(fields)
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail="A portfolio with this name already exists.") from exc
        portfolio_id = str(document["_id"])
        if user["role"] == "portfolio_leader":
            await self.repo.assign(user["_id"], portfolio_id)
        await self.accounts.repo.audit(user["name"], "create", portfolio_id, f"Created portfolio {data.name}.")
        return await self.present(document)

    async def update(self, user: dict, portfolio_id: str, data: PortfolioInput) -> PortfolioResponse:
        """Update an authorized portfolio and audit the change."""
        previous = await self.get(user, portfolio_id, "edit")
        fields = data.model_dump()
        fields["name_key"] = data.name.casefold()
        try:
            document = await self.repo.update(portfolio_id, fields)
        except DuplicateKeyError as exc:
            raise HTTPException(status_code=409, detail="A portfolio with this name already exists.") from exc
        if not document:
            raise HTTPException(status_code=404, detail="Portfolio not found.")
        action = "archive" if previous["status"] != "Archived" and data.status == "Archived" else "edit"
        verb = "Archived" if action == "archive" else "Edited"
        await self.accounts.repo.audit(user["name"], action, portfolio_id, f"{verb} portfolio {data.name}.")
        return await self.present(document)

    async def archive(self, user: dict, portfolio_id: str) -> PortfolioResponse:
        """Archive an authorized portfolio without removing applications."""
        document = await self.get(user, portfolio_id, "edit")
        fields = {key: document[key] for key in ("name", "owner", "product_area", "description")}
        return await self.update(user, portfolio_id, PortfolioInput(**fields, status="Archived"))

    async def delete(self, user: dict, portfolio_id: str) -> None:
        """Delete an empty portfolio for an authorized administrator."""
        document = await self.get(user, portfolio_id, "delete")
        if await self.repo.application_count(portfolio_id):
            raise HTTPException(status_code=409, detail="Move or delete the applications first, or archive the portfolio instead.")
        if not await self.repo.delete(portfolio_id):
            raise HTTPException(status_code=404, detail="Portfolio not found.")
        await self.repo.remove_assignments(portfolio_id)
        await self.accounts.repo.audit(user["name"], "delete", portfolio_id, f"Deleted portfolio {document['name']}.")
