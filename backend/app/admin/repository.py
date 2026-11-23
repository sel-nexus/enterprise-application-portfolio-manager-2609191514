"""Persist administration data using the shared MongoDB database."""
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

class AdminRepository:
    """Access people, roles, settings and audit history."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the application database."""
        self.db = db

    async def users(self, page: int, size: int) -> tuple[list[dict], int]:
        """Return a bounded page without password hashes."""
        total = await self.db.users.count_documents({})
        docs = await self.db.users.find({}, {'password_hash': 0}).sort([('name', 1), ('_id', 1)]).skip((page - 1) * size).limit(size).to_list(None)
        return docs, total

    async def user(self, identifier: str) -> dict | None:
        """Find a user by public identifier."""
        return await self.db.users.find_one({'_id': ObjectId(identifier)}) if ObjectId.is_valid(identifier) else None

    async def portfolios_valid(self, ids: list[str]) -> bool:
        """Verify all assigned portfolio references exist."""
        return all(ObjectId.is_valid(x) for x in ids) and await self.db.portfolios.count_documents({'_id': {'$in': [ObjectId(x) for x in ids]}}) == len(set(ids))

    async def audit_page(self, query: dict, page: int, size: int) -> tuple[list[dict], int]:
        """Return audit entries newest first."""
        total = await self.db.audit.count_documents(query)
        docs = await self.db.audit.find(query).sort([('when', -1), ('_id', -1)]).skip((page - 1) * size).limit(size).to_list(None)
        return docs, total
