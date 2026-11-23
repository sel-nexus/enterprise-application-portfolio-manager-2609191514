"""Validate administration requests."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

RoleName = Literal['administrator', 'portfolio_leader', 'engineer', 'executive', 'auditor', 'read_only']

class UserInput(BaseModel):
    """Describe a person's access and profile."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    role: RoleName
    portfolio_ids: list[str] = Field(default_factory=list, max_length=200)
    vendor_staff: bool = False
    manager: str = Field(default='', max_length=200)

class UserCreate(UserInput):
    """Require an administrator-provided temporary credential."""
    temporary_password: str = Field(min_length=12, max_length=72)

    @field_validator('temporary_password')
    @classmethod
    def valid_password(cls, value: str) -> str:
        """Enforce password strength and bcrypt's byte limit."""
        if len(value.encode()) > 72 or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError('Use at least 12 characters including a letter and a number, maximum 72 bytes.')
        return value

class Permissions(BaseModel):
    """Represent the six independently restrictable actions."""
    model_config = ConfigDict(extra='forbid')
    view: bool
    create: bool
    edit: bool
    delete: bool
    export: bool
    administer: bool

class RoleInput(BaseModel):
    """Accept a role description and its restricted permissions."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    description: str = Field(max_length=1000)
    permissions: Permissions
