"""Persist reviews and query the eligible estate."""
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class ReviewRepository:
    """Access review, assignment and interval documents."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the shared database."""
        self.db = db

    async def indexes(self) -> None:
        """Index deterministic application history."""
        await self.db.reviews.create_index([('application_id', 1), ('date', -1), ('created_at', -1), ('_id', -1)])

    async def create(self, fields: dict) -> dict:
        """Persist a review with a creation timestamp."""
        fields['created_at'] = datetime.now(timezone.utc)
        result = await self.db.reviews.insert_one(fields)
        return await self.db.reviews.find_one({'_id': result.inserted_id})

    async def history(self, application_id: str, page: int, page_size: int) -> tuple[list[dict], int]:
        """Return newest reviews in a stable order."""
        query = {'application_id': application_id}
        total = await self.db.reviews.count_documents(query)
        docs = await self.db.reviews.find(query).sort([('date', -1), ('created_at', -1), ('_id', -1)]).skip((page - 1) * page_size).limit(page_size).to_list(None)
        return docs, total

    async def interval(self) -> int:
        """Return the stored interval or the initial default."""
        doc = await self.db.settings.find_one({'_id': 'review_interval'})
        return doc['days'] if doc else 90

    async def set_interval(self, days: int) -> None:
        """Persist the administrator's interval."""
        await self.db.settings.update_one({'_id': 'review_interval'}, {'$set': {'days': days}}, upsert=True)

    async def eligible_users(self) -> list[dict]:
        """Find active accounts that may be eligible for assignment."""
        return await self.db.users.find({'active': True, 'role': {'$in': ['administrator', 'portfolio_leader', 'engineer']}}, {'name': 1, 'role': 1, 'active': 1, 'portfolio_ids': 1}).sort([('name', 1), ('_id', 1)]).to_list(None)

    async def estate(self, scope: list[str] | None, portfolio_id: str) -> list[dict]:
        """Load scoped active portfolios and their eligible applications."""
        query: dict = {'status': 'Active'}
        ids = scope if not portfolio_id else ([portfolio_id] if scope is None or portfolio_id in scope else [])
        if ids is not None:
            query['_id'] = {'$in': [ObjectId(x) for x in ids if ObjectId.is_valid(x)]}
        portfolios = await self.db.portfolios.find(query).to_list(None)
        for portfolio in portfolios:
            pid = str(portfolio['_id'])
            portfolio['applications'] = await self.db.applications.find({'portfolio_id': pid, 'lifecycle': {'$in': ['Active', 'Deprecated']}}).to_list(None)
        return portfolios

    async def assign(self, application_id: str, portfolio_id: str, reviewer: dict | None) -> dict | None:
        """Store a reviewer snapshot if the authorized portfolio is unchanged."""
        return await self.db.applications.find_one_and_update({'_id': ObjectId(application_id), 'portfolio_id': portfolio_id}, {'$set': {'assigned_reviewer_id': str(reviewer['_id']) if reviewer else None, 'assigned_reviewer_name': reviewer['name'] if reviewer else None}}, return_document=True)
