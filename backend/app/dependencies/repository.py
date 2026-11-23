"""Persist and query directional application links."""
import re
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class DependencyRepository:
    """Access dependency documents and scoped estate summaries."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the shared Mongo database."""
        self.db = db

    async def indexes(self) -> None:
        """Enforce unique directional triples and support reverse lookup."""
        await self.db.dependencies.create_index([('from_application_id', 1), ('relationship', 1), ('to_application_id', 1)], unique=True)
        await self.db.dependencies.create_index('to_application_id')

    async def create(self, fields: dict) -> dict:
        """Store and return a link."""
        result = await self.db.dependencies.insert_one(fields.copy())
        return await self.db.dependencies.find_one({'_id': result.inserted_id})

    async def get(self, link_id: str) -> dict | None:
        """Find a link by identifier."""
        if not ObjectId.is_valid(link_id):
            return None
        return await self.db.dependencies.find_one({'_id': ObjectId(link_id)})

    async def delete(self, link_id: str) -> bool:
        """Remove a link if it still exists."""
        return bool((await self.db.dependencies.delete_one({'_id': ObjectId(link_id)})).deleted_count)

    async def visible_applications(self, scope: list[str] | None) -> list[dict]:
        """Fetch identities in visible portfolios, including archived and retired records."""
        query = {} if scope is None else {'portfolio_id': {'$in': scope}}
        return await self.db.applications.find(query, {'name': 1, 'portfolio_id': 1, 'lifecycle': 1}).to_list(None)

    async def list_links(self, ids: list[str], search: str, relationship: str, portfolio_ids: list[str] | None, application_id: str, direction: str, page: int, page_size: int, names: dict[str, dict]) -> tuple[list[dict], int]:
        """Find and paginate links whose two endpoints are visible."""
        query: dict = {'from_application_id': {'$in': ids}, 'to_application_id': {'$in': ids}}
        if relationship:
            query['relationship'] = relationship
        if portfolio_ids is not None:
            query['to_application_id'] = {'$in': portfolio_ids}
        if application_id:
            query['$and'] = [{('from_application_id' if direction == 'outgoing' else 'to_application_id'): application_id}]
        if search:
            pattern = re.compile(re.escape(search), re.IGNORECASE)
            matched = [key for key, value in names.items() if pattern.search(value['name'])]
            query['$or'] = [{'from_application_id': {'$in': matched}}, {'to_application_id': {'$in': matched}}, {'note': {'$regex': re.escape(search), '$options': 'i'}}]
        total = await self.db.dependencies.count_documents(query)
        docs = await self.db.dependencies.find(query).sort('_id', 1).skip((page - 1) * page_size).limit(page_size).to_list(None)
        return docs, total

    async def links_for_summary(self, ids: list[str]) -> list[dict]:
        """Read only visible endpoint identifiers for summary calculations."""
        return await self.db.dependencies.find({'from_application_id': {'$in': ids}, 'to_application_id': {'$in': ids}}, {'from_application_id': 1, 'to_application_id': 1}).to_list(None)

    async def portfolios(self, ids: list[str]) -> dict[str, str]:
        """Resolve portfolio names for visible identities."""
        cursor = self.db.portfolios.find({'_id': {'$in': [ObjectId(p) for p in ids if ObjectId.is_valid(p)]}}, {'name': 1})
        return {str(doc['_id']): doc['name'] async for doc in cursor}
