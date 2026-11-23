"""Persist and query application inventory in MongoDB."""

import re
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class ApplicationRepository:
    """Access applications and their referenced records."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the shared database."""
        self.db = db

    async def indexes(self) -> None:
        """Enforce case-insensitive normalized names and index scope filters."""
        await self.db.applications.create_index('name_key', unique=True)
        await self.db.applications.create_index([('portfolio_id', 1), ('lifecycle', 1)])

    async def get(self, application_id: str) -> dict | None:
        """Find an application by its public identifier."""
        if not ObjectId.is_valid(application_id):
            return None
        return await self.db.applications.find_one({'_id': ObjectId(application_id)})

    async def portfolio(self, portfolio_id: str) -> dict | None:
        """Find the referenced portfolio."""
        if not ObjectId.is_valid(portfolio_id):
            return None
        return await self.db.portfolios.find_one({'_id': ObjectId(portfolio_id)})

    async def list(self, scope: list[str] | None, search: str, portfolio_id: str, criticality: str, lifecycle: str, include_archived: bool, page: int, page_size: int) -> tuple[list[dict], int]:
        """Return a page within the permitted portfolio and lifecycle scope."""
        portfolios: dict = {} if include_archived else {'status': 'Active'}
        if scope is not None:
            portfolios['_id'] = {'$in': [ObjectId(p) for p in scope if ObjectId.is_valid(p)]}
        if portfolio_id:
            if not ObjectId.is_valid(portfolio_id):
                return [], 0
            portfolios['_id'] = {'$in': [ObjectId(portfolio_id)] if scope is None or portfolio_id in scope else []}
        ids = [str(p['_id']) async for p in self.db.portfolios.find(portfolios, {'_id': 1})]
        query: dict = {'portfolio_id': {'$in': ids}}
        if search:
            pattern = re.escape(search)
            query['$or'] = [{'name': {'$regex': pattern, '$options': 'i'}}, {'business_owner': {'$regex': pattern, '$options': 'i'}}]
        if criticality != 'All':
            query['criticality'] = criticality
        query['lifecycle'] = {'$in': ['Active', 'Deprecated']} if lifecycle == 'Default' else ({'$in': ['Active', 'Deprecated', 'Retired']} if lifecycle == 'All' else lifecycle)
        total = await self.db.applications.count_documents(query)
        cursor = self.db.applications.find(query).sort([('name_key', 1), ('_id', 1)]).skip((page - 1) * page_size).limit(page_size)
        return await cursor.to_list(None), total

    async def create(self, fields: dict) -> dict:
        """Insert and reload an application."""
        result = await self.db.applications.insert_one(fields)
        return await self.db.applications.find_one({'_id': result.inserted_id})

    async def update(self, application_id: str, fields: dict, expected_portfolio: str) -> dict | None:
        """Update only if the portfolio has not changed since authorization."""
        if not ObjectId.is_valid(application_id):
            return None
        return await self.db.applications.find_one_and_update({'_id': ObjectId(application_id), 'portfolio_id': expected_portfolio}, {'$set': fields}, return_document=True)

    async def delete(self, application_id: str) -> bool:
        """Delete the application and related reviews and directional links."""
        result = await self.db.applications.delete_one({'_id': ObjectId(application_id)})
        if not result.deleted_count:
            return False
        await self.db.reviews.delete_many({'application_id': application_id})
        await self.db.dependencies.delete_many({'$or': [{'from_application_id': application_id}, {'to_application_id': application_id}]})
        return True
