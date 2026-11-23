"""Expose the application-owned MongoDB connection."""

from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase


def get_database(request: Request) -> AsyncDatabase:
    """Return the database associated with the running application."""
    return request.app.state.db
