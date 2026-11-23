"""Validate review and assignment requests."""
from datetime import date as Date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.text_validation import reject_markup


class ReviewInput(BaseModel):
    """Capture a dated assessment of an application."""
    model_config = ConfigDict(extra='forbid')
    date: Date = Field(default_factory=Date.today)
    health: float = Field(ge=0, le=100, allow_inf_nan=False, strict=True)
    quality: float = Field(ge=0, le=100, allow_inf_nan=False, strict=True)
    automation_coverage: float = Field(ge=0, le=100, allow_inf_nan=False, strict=True)
    unit_test_coverage: float = Field(ge=0, le=100, allow_inf_nan=False, strict=True)
    open_defects: int = Field(ge=0, strict=True)
    open_critical_defects: int = Field(ge=0, strict=True)
    risk: Literal['Low', 'Medium', 'High']
    note: str = Field(default='', max_length=4000)

    @field_validator('note')
    @classmethod
    def validate_note(cls, value: str) -> str:
        """Reject markup in new review notes."""
        return reject_markup(value)

    @field_validator('date')
    @classmethod
    def not_future(cls, value: Date) -> Date:
        """Reject future assessments."""
        if value > Date.today():
            raise ValueError('Review date cannot be in the future.')
        return value

    @model_validator(mode='after')
    def valid_defects(self):
        """Ensure critical defects are included in the total."""
        if self.open_critical_defects > self.open_defects:
            raise ValueError('Critical defects cannot exceed open defects.')
        return self


class AssignmentInput(BaseModel):
    """Choose an eligible account or clear the assignment."""
    model_config = ConfigDict(extra='forbid')
    reviewer_id: str | None = Field(default=None, max_length=100)


class IntervalInput(BaseModel):
    """Validate the administrator's review interval."""
    model_config = ConfigDict(extra='forbid')
    days: int = Field(ge=30, le=365, strict=True)
