"""Define public account and authentication contracts."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

Landing = Literal["dashboard", "applications", "reviews_due"]


class LoginRequest(BaseModel):
    """Accept a sign-in attempt."""
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    """Validate a confirmed replacement password."""
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=72)
    confirm_password: str = Field(max_length=72)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        """Require a letter, a number and bcrypt's byte limit."""
        if len(value.encode()) > 72 or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Use at least 12 characters including a letter and a number (maximum 72 bytes).")
        return value

    @model_validator(mode="after")
    def matching_passwords(self) -> "PasswordChange":
        """Reject mismatched confirmation or the existing password."""
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        if self.new_password == self.current_password:
            raise ValueError("Choose a different password.")
        return self


class Preferences(BaseModel):
    """Accept a landing-page choice."""
    landing_page: Landing


class AccountResponse(BaseModel):
    """Expose non-secret account information."""
    id: str
    name: str
    email: str
    role: str
    portfolio_ids: list[str]
    last_sign_in: datetime | None = None
    landing_page: Landing


class TokenResponse(BaseModel):
    """Describe the signed session and required next step."""
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    must_change_password: bool


class Message(BaseModel):
    """Return an operation status."""
    message: str
