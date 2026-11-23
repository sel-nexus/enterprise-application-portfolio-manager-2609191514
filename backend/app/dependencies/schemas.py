"""Validate directional application dependencies."""
from typing import Literal
from pydantic import BaseModel, Field

Relationship = Literal['Calls', 'Receives data from', 'Needs at runtime']


class DependencyInput(BaseModel):
    """Describe a directional link between two applications."""
    from_application_id: str = Field(min_length=1, max_length=24)
    relationship: Relationship
    to_application_id: str = Field(min_length=1, max_length=24)
    note: str = Field(default='', max_length=2000)
