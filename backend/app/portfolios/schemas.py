"""Define portfolio inventory request and response contracts."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Status = Literal["Active", "Archived"]


class PortfolioInput(BaseModel):
    """Validate editable portfolio identity fields."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    owner: str = Field(min_length=1, max_length=200)
    product_area: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: Status = "Active"


class PortfolioResponse(PortfolioInput):
    """Return a portfolio and the count of its stored applications."""
    id: str
    application_count: int


class PortfolioPage(BaseModel):
    """Return a bounded portfolio list and its pagination metadata."""
    items: list[PortfolioResponse]
    total: int
    page: int
    page_size: int
