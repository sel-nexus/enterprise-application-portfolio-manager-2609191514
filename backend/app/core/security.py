"""Provide password, signed-token, and authorization primitives."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings

ALL_PORTFOLIOS = {"administrator", "executive", "auditor"}
ROLE_ACTIONS = {
    "administrator": {"view", "create", "edit", "delete", "export", "administer", "audit"},
    "portfolio_leader": {"view", "create", "edit", "export"},
    "engineer": {"view", "create", "edit", "export"},
    "executive": {"view", "export"},
    "auditor": {"view", "export", "audit"},
    "read_only": {"view"},
}


async def hash_password(password: str) -> str:
    """Hash a password without blocking the event loop."""
    return (await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt())).decode()


async def verify_password(password: str, password_hash: str) -> bool:
    """Check a password without blocking the event loop."""
    if len(password.encode()) > 72:
        return False
    try:
        return await asyncio.to_thread(bcrypt.checkpw, password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user_id: str, purpose: str) -> tuple[str, str, datetime]:
    """Issue a signed, time-limited token and its session identifier."""
    now = datetime.now(timezone.utc)
    expiry = now + (timedelta(minutes=15) if purpose == "setup" else timedelta(hours=8))
    session_id = uuid4().hex
    token = jwt.encode({"sub": user_id, "jti": session_id, "purpose": purpose, "iat": now, "exp": expiry}, settings.jwt_secret, algorithm="HS256")
    return token, session_id, expiry


def decode_token(token: str) -> dict[str, Any]:
    """Validate a token's signature, expiry and mandatory claims."""
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["sub", "jti", "purpose", "iat", "exp"]})


def can_access(user: dict, action: str, portfolio_id: str | None = None, permissions: dict | None = None, resource: str | None = None) -> bool:
    """Apply the shipped role ceiling, stored restrictions and portfolio scope."""
    role = user.get("role")
    if not user.get("active") or action not in ROLE_ACTIONS.get(role, set()):
        return False
    permission_name = "view" if action == "audit" else action
    if permissions is not None and not permissions.get(permission_name, False):
        return False
    if resource == "audit" and role not in {"administrator", "auditor"}:
        return False
    if resource == "portfolio" and action in {"create", "edit"} and role not in {"administrator", "portfolio_leader"}:
        return False
    if action == "delete" and role != "administrator":
        return False
    if portfolio_id is not None and role not in ALL_PORTFOLIOS and portfolio_id not in [str(p) for p in user.get("portfolio_ids", [])]:
        return False
    return True
