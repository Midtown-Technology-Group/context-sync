"""Base models for Graph API responses.

Provides shared functionality and type safety for all source data.
"""
from __future__ import annotations

from typing import Generic, TypeVar
from pydantic import BaseModel, Field


class BaseSourceModel(BaseModel):
    """Base model for all Graph API entity models.
    
    Provides common configuration and utilities.
    """
    
    class Config:
        """Pydantic configuration."""
        populate_by_name = True  # Allow both alias and field name
        str_strip_whitespace = True
        extra = "ignore"  # Ignore unexpected fields from Graph API


class BaseSourceResult(BaseModel):
    """Base model for source fetcher results.
    
    Wraps the raw API response with metadata.
    """
    value: list[BaseSourceModel] = Field(default_factory=list)
    error: str | None = None
    
    @property
    def has_error(self) -> bool:
        """Check if result contains an error."""
        return self.error is not None
    
    @property
    def count(self) -> int:
        """Return number of items."""
        return len(self.value)


T = TypeVar("T", bound=BaseSourceModel)


class TypedSourceResult(BaseSourceResult, Generic[T]):
    """Generic source result with typed items.
    
    Usage:
        result: TypedSourceResult[CalendarEvent]
    """
    value: list[T] = Field(default_factory=list)
