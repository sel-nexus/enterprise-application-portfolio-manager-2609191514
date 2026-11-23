"""Implement sign-in, account updates, and session enforcement."""

from datetime import datetime, timezone
from fastapi import HTTPException
from jwt import PyJWTError

from app.accounts.repository import AccountRepository
from app.accounts.schemas import AccountResponse, LoginRequest, PasswordChange, TokenResponse
from app.core.security import ALL_PORTFOLIOS, can_access, create_token, hash_password, verify_password
from app.core.security import decode_token


class AccountService:
    """Coordinate persistent account operations."""

    def __init__(self, repository: AccountRepository) -> None:
        """Bind the account repository."""
        self.repo = repository

    async def issue(self, user: dict, purpose: str) -> TokenResponse:
        """Create a revocable signed session."""
        token, session_id, expires = create_token(str(user["_id"]), purpose)
        await self.repo.create_session(session_id, user, expires, purpose)
        return TokenResponse(access_token=token, must_change_password=purpose == "setup")

    async def login(self, data: LoginRequest) -> TokenResponse:
        """Authenticate an active account and audit the outcome."""
        email = str(data.email).strip().lower()
        user = await self.repo.by_email(email)
        valid = user is not None and await verify_password(data.password, user["password_hash"])
        if not valid or not user.get("active", False):
            await self.repo.audit(email, "failed_sign_in", email, "Sign-in failed.")
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        await self.repo.update(user["_id"], {"last_sign_in": datetime.now(timezone.utc)})
        await self.repo.audit(user["name"], "sign_in", str(user["_id"]), "Signed in.")
        return await self.issue(user, "setup" if user.get("must_change_password", False) else "access")

    async def authenticate(self, token: str, allow_setup: bool = False) -> tuple[dict, dict]:
        """Reject invalid, revoked, inactive, or insufficient sessions."""
        try:
            claims = decode_token(token)
            purpose = claims.get("purpose")
            if purpose not in ({"access", "setup"} if allow_setup else {"access"}):
                raise ValueError("Invalid session purpose")
            user = await self.repo.by_id(claims["sub"])
            if not user or not user.get("active") or not await self.repo.session(claims["jti"], user, purpose):
                raise ValueError("Session no longer valid")
            if purpose == "access" and user.get("must_change_password"):
                raise ValueError("Password change required")
            return user, claims
        except (PyJWTError, ValueError, KeyError, TypeError):
            raise HTTPException(status_code=401, detail="Invalid or expired session.", headers={"WWW-Authenticate": "Bearer"}) from None

    async def account(self, user: dict) -> AccountResponse:
        """Expose effective role permissions and the default landing page."""
        default = "dashboard" if user["role"] in {"administrator", "executive"} else "applications"
        role = await self.repo.db.roles.find_one({"name": user["role"]})
        restrictions = role.get("permissions") if role else None
        permissions = {action: can_access(user, action, permissions=restrictions) for action in ("view", "create", "edit", "delete", "export", "administer")}
        return AccountResponse(id=str(user["_id"]), name=user["name"], email=user["email"], role=user["role"], permissions=permissions, portfolio_ids=[str(p) for p in user.get("portfolio_ids", [])], last_sign_in=user.get("last_sign_in"), landing_page=user.get("landing_page") or default)

    async def change_password(self, user: dict, data: PasswordChange) -> TokenResponse:
        """Verify the current password and replace all prior sessions."""
        if not await verify_password(data.current_password, user["password_hash"]):
            raise HTTPException(status_code=400, detail="The current password is incorrect.")
        new_hash = await hash_password(data.new_password)
        if not await self.repo.change_password(user, new_hash):
            raise HTTPException(status_code=409, detail="Account changed. Sign in again.")
        await self.repo.audit(user["name"], "edit", str(user["_id"]), "Changed account password.")
        updated = await self.repo.by_id(str(user["_id"]))
        return await self.issue(updated, "access")

    async def set_landing(self, user: dict, landing: str) -> AccountResponse:
        """Persist a person's landing-page selection."""
        await self.repo.update(user["_id"], {"landing_page": landing})
        await self.repo.audit(user["name"], "edit", str(user["_id"]), "Changed landing page.")
        user["landing_page"] = landing
        return await self.account(user)

    async def authorize(self, user: dict, action: str, portfolio_id: str | None = None, resource: str | None = None) -> None:
        """Enforce role and portfolio restrictions for later feature routes."""
        role = await self.repo.db.roles.find_one({"name": user["role"]})
        restrictions = role.get("permissions") if role else None
        if not can_access(user, action, portfolio_id, restrictions, resource):
            raise HTTPException(status_code=403, detail="Not permitted.")

    def portfolio_scope(self, user: dict) -> list[str] | None:
        """Return allowed portfolio IDs or None for organization-wide access."""
        return None if user.get("role") in ALL_PORTFOLIOS else [str(p) for p in user.get("portfolio_ids", [])]
