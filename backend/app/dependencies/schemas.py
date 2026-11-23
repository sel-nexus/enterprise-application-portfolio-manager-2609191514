"""Validate directional application dependencies."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator

from app.core.text_validation import reject_markup

Relationship = Literal['Calls', 'Receives data from', 'Needs at runtime']


class DependencyInput(BaseModel):
    """Describe a directional link between two applications."""
    from_application_id: str = Field(min_length=1, max_length=24)
    relationship: Relationship
    to_application_id: str = Field(min_length=1, max_length=24)
    note: str = Field(default='', max_length=2000)

    @field_validator('note')
    @classmethod
    def validate_note(cls, value: str) -> str:
        """Reject markup in new dependency notes."""
        return reject_markup(value)
