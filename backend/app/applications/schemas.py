"""Define application identity and lifecycle API contracts."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Criticality = Literal['Low', 'Medium', 'High', 'Critical']
Lifecycle = Literal['Active', 'Deprecated', 'Retired']


class ApplicationInput(BaseModel):
    """Validate identity independently of review-derived measurements."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)
    portfolio_id: str = Field(min_length=1, max_length=100)
    product_area: str = Field(default='', max_length=200)
    business_owner: str = Field(default='', max_length=200)
    technology_owner: str = Field(default='', max_length=200)
    inventory_owner: str = Field(default='', max_length=200)
    criticality: Criticality = 'Medium'
    tier: int = Field(ge=1, le=4, strict=True)
    technology_stack: str = Field(default='', max_length=2000)


class LifecycleInput(BaseModel):
    """Validate a lifecycle change."""
    model_config = ConfigDict(extra='forbid')
    lifecycle: Lifecycle


class ApplicationResponse(ApplicationInput):
    """Expose stored identity and lifecycle."""
    id: str
    lifecycle: Lifecycle
    portfolio_name: str


class ApplicationPage(BaseModel):
    """Return a bounded page of applications."""
    items: list[ApplicationResponse]
    total: int
    page: int
    page_size: int
