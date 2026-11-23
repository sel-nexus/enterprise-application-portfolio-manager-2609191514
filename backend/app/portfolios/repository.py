"""Persist portfolio identities and related inventory counts in MongoDB."""

import re
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class PortfolioRepository:
    """Access portfolio documents using the shared database."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the shared database."""
        self.db = db

    async def indexes(self) -> None:
        """Enforce normalized unique names and index common filters."""
        await self.db.portfolios.create_index("name_key", unique=True)
        await self.db.portfolios.create_index([("status", 1), ("name_key", 1)])
        await self.db.applications.create_index("portfolio_id")

    async def get(self, portfolio_id: str) -> dict | None:
        """Find a portfolio by its public identifier."""
        if not ObjectId.is_valid(portfolio_id):
            return None
        return await self.db.portfolios.find_one({"_id": ObjectId(portfolio_id)})

    async def list(self, scope: list[str] | None, search: str, status: str, page: int, page_size: int) -> tuple[list[dict], int]:
        """Query only the requested page within the authorized scope."""
        query: dict = {}
        if scope is not None:
            query["_id"] = {"$in": [ObjectId(value) for value in scope if ObjectId.is_valid(value)]}
        if status != "All":
            query["status"] = status
        if search:
            pattern = re.escape(search)
            query["$or"] = [{"name": {"$regex": pattern, "$options": "i"}}, {"owner": {"$regex": pattern, "$options": "i"}}]
        total = await self.db.portfolios.count_documents(query)
        cursor = self.db.portfolios.find(query).sort([("name_key", 1), ("_id", 1)]).skip((page - 1) * page_size).limit(page_size)
        return await cursor.to_list(None), total

    async def create(self, fields: dict) -> dict:
        """Insert and return a portfolio document."""
        result = await self.db.portfolios.insert_one(fields)
        return await self.db.portfolios.find_one({"_id": result.inserted_id})

    async def update(self, portfolio_id: str, fields: dict) -> dict | None:
        """Replace editable fields and return the updated document."""
        if not ObjectId.is_valid(portfolio_id):
            return None
        return await self.db.portfolios.find_one_and_update({"_id": ObjectId(portfolio_id)}, {"$set": fields}, return_document=True)

    async def application_count(self, portfolio_id: str) -> int:
        """Count every application, including retired ones."""
        return await self.db.applications.count_documents({"portfolio_id": portfolio_id})

    async def delete(self, portfolio_id: str) -> bool:
        """Remove the identified portfolio."""
        result = await self.db.portfolios.delete_one({"_id": ObjectId(portfolio_id)})
        return result.deleted_count == 1

    async def assign(self, user_id: ObjectId, portfolio_id: str) -> None:
        """Add a newly created portfolio to the leader's scope."""
        await self.db.users.update_one({"_id": user_id}, {"$addToSet": {"portfolio_ids": portfolio_id}})

    async def remove_assignments(self, portfolio_id: str) -> None:
        """Remove deleted portfolio references from accounts."""
        await self.db.users.update_many({"portfolio_ids": portfolio_id}, {"$pull": {"portfolio_ids": portfolio_id}})
