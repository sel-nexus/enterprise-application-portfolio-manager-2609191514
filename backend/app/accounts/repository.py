"""Persist accounts, sessions, and audit entries in MongoDB."""

from datetime import datetime, timezone
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class AccountRepository:
    """Provide database operations needed by account services."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind operations to the pooled application database."""
        self.db = db

    async def indexes(self) -> None:
        """Create uniqueness and session-expiry indexes."""
        await self.db.users.create_index("email", unique=True)
        await self.db.sessions.create_index("expires_at", expireAfterSeconds=0)
        await self.db.audit.create_index("when")

    async def bootstrap(self, email: str, name: str, password_hash: str) -> None:
        """Insert the initial administrator only when absent."""
        await self.db.users.update_one({"email": email}, {"$setOnInsert": {"email": email, "name": name, "password_hash": password_hash, "role": "administrator", "portfolio_ids": [], "active": True, "must_change_password": True, "token_version": 0, "last_sign_in": None}}, upsert=True)

    async def by_email(self, email: str) -> dict | None:
        """Find an account by normalized email."""
        return await self.db.users.find_one({"email": email})

    async def by_id(self, user_id: str) -> dict | None:
        """Find an account by its public identifier."""
        if not ObjectId.is_valid(user_id):
            return None
        return await self.db.users.find_one({"_id": ObjectId(user_id)})

    async def update(self, user_id: ObjectId, fields: dict) -> None:
        """Update stored account fields."""
        await self.db.users.update_one({"_id": user_id}, {"$set": fields})

    async def change_password(self, user: dict, password_hash: str) -> bool:
        """Change the password once and invalidate previously issued sessions."""
        result = await self.db.users.update_one({"_id": user["_id"], "password_hash": user["password_hash"], "active": True}, {"$set": {"password_hash": password_hash, "must_change_password": False}, "$inc": {"token_version": 1}})
        return result.modified_count == 1

    async def create_session(self, session_id: str, user: dict, expires: datetime, purpose: str) -> None:
        """Persist an individually revocable token session."""
        await self.db.sessions.insert_one({"_id": session_id, "user_id": user["_id"], "token_version": user.get("token_version", 0), "purpose": purpose, "expires_at": expires})

    async def session(self, session_id: str, user: dict, purpose: str) -> dict | None:
        """Look up a live session belonging to the current account version."""
        return await self.db.sessions.find_one({"_id": session_id, "user_id": user["_id"], "purpose": purpose, "token_version": user.get("token_version", 0), "expires_at": {"$gt": datetime.now(timezone.utc)}})

    async def revoke(self, session_id: str) -> None:
        """Revoke one session."""
        await self.db.sessions.delete_one({"_id": session_id})

    async def audit(self, who: str, action: str, record: str, summary: str) -> None:
        """Persist a concise account event without secrets."""
        await self.db.audit.insert_one({"when": datetime.now(timezone.utc), "who": who, "action": action, "record": record, "summary": summary})
