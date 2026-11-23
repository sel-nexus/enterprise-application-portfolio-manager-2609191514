"""Read reporting source documents from the shared Mongo database."""
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class ReportingRepository:
    """Read only portfolios in the caller's authorized scope."""
    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the pooled database."""
        self.db = db

    async def estate(self, scope: list[str] | None) -> tuple[list[dict], list[dict], dict[str, int], int]:
        """Load scoped identities, deterministic latest reviews and visible links."""
        query = {} if scope is None else {'_id': {'$in': [ObjectId(x) for x in scope if ObjectId.is_valid(x)]}}
        portfolios = await self.db.portfolios.find(query).sort([('name', 1), ('_id', 1)]).to_list(None)
        ids = [str(p['_id']) for p in portfolios]
        pipeline = [
            {'$match': {'portfolio_id': {'$in': ids}}},
            {'$lookup': {'from': 'reviews', 'let': {'aid': {'$toString': '$_id'}}, 'pipeline': [
                {'$match': {'$expr': {'$eq': ['$application_id', '$$aid']}}},
                {'$sort': {'date': -1, 'created_at': -1, '_id': -1}}, {'$limit': 1}], 'as': 'latest'}},
            {'$sort': {'name': 1, '_id': 1}},
        ]
        apps = await (await self.db.applications.aggregate(pipeline)).to_list(None)
        visible_ids = [str(a['_id']) for a in apps]
        links = self.db.dependencies.find({'from_application_id': {'$in': visible_ids}, 'to_application_id': {'$in': visible_ids}}, {'from_application_id': 1})
        counts: dict[str, int] = {}
        async for link in links:
            key = link['from_application_id']
            counts[key] = counts.get(key, 0) + 1
        setting = await self.db.settings.find_one({'_id': 'review_interval'})
        return portfolios, apps, counts, setting['days'] if setting else 90
