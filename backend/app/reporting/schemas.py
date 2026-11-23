"""Define validated reporting filters and result shapes."""
from typing import Literal
from pydantic import BaseModel, Field


class Filters(BaseModel):
    """Restrict report queries to supported inventory filters."""
    portfolio_id: str = Field(default='', max_length=100)
    product_area: str = Field(default='', max_length=200)
    risk: Literal['All', 'Low', 'Medium', 'High', 'No review'] = 'All'
    search: str = Field(default='', max_length=200)
    criticality: Literal['All', 'Low', 'Medium', 'High', 'Critical'] = 'All'
    lifecycle: Literal['Default', 'All', 'Active', 'Deprecated', 'Retired'] = 'Default'
    include_archived: bool = False


class Page(BaseModel):
    """Describe a bounded report page."""
    items: list[dict]
    total: int
    page: int
    page_size: int
