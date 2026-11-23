"""Create the API and manage its MongoDB connection."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient

from app.accounts.repository import AccountRepository
from app.accounts.router import router
from app.core.config import settings
from app.core.security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one pooled client, initialize indexes and optionally bootstrap."""
    settings.validate_security()
    client = AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        app.state.db = client.get_database(settings.mongodb_db)
        repo = AccountRepository(app.state.db)
        await repo.indexes()
        if settings.bootstrap_email:
            await repo.bootstrap(settings.bootstrap_email.strip().lower(), settings.bootstrap_name, await hash_password(settings.bootstrap_password))
        yield
    finally:
        await client.close()


app = FastAPI(title="Enterprise Application Portfolio Manager", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()], allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
app.include_router(router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report process liveness without querying dependencies."""
    return {"status": "ok"}
