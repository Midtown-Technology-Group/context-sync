"""Todo task models for Microsoft Graph API.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator

from .base import BaseSourceModel


class TaskStatus(StrEnum):
    """Todo task status values."""
    NOT_STARTED = "notStarted"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    WAITING_ON_OTHERS = "waitingOnOthers"
    DEFERRED = "deferred"


class TaskImportance(StrEnum):
    """Todo task importance levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class DateTimeTimeZone(BaseModel):
    """Graph API date/time with timezone."""
    date_time: datetime | str = Field(alias="dateTime")
    time_zone: str = Field(alias="timeZone")
    
    @field_validator("date_time", mode="before")
    @classmethod
    def parse_datetime(cls, v: datetime | str) -> datetime | str:
        """Parse ISO datetime strings."""
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return v
        return v


class TodoTask(BaseSourceModel):
    """Microsoft Graph Todo task.
    
    Tracks task completion, importance, and due dates.
    """
    id: str
    title: str = "(untitled task)"
    status: TaskStatus = TaskStatus.NOT_STARTED
    importance: TaskImportance = TaskImportance.NORMAL
    is_important: bool = Field(alias="isImportant", default=False)  # Graph API alias
    created_date_time: datetime | str | None = Field(alias="createdDateTime", default=None)
    last_modified_date_time: datetime | str | None = Field(alias="lastModifiedDateTime", default=None)
    completed_date_time: DateTimeTimeZone | None = Field(alias="completedDateTime", default=None)
    due_date_time: DateTimeTimeZone | None = Field(alias="dueDateTime", default=None)
    reminder_date_time: DateTimeTimeZone | None = Field(alias="reminderDateTime", default=None)
    body: dict[str, Any] = Field(default_factory=dict)
    categories: list[str] = Field(default_factory=list)
    list_name: str = "(list)"  # Populated by fetcher, not from API
    
    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: str | TaskStatus) -> TaskStatus:
        """Ensure status is valid enum value."""
        if isinstance(v, TaskStatus):
            return v
        try:
            return TaskStatus(v)
        except ValueError:
            return TaskStatus.NOT_STARTED
    
    @field_validator("importance", mode="before")
    @classmethod
    def validate_importance(cls, v: str | TaskImportance) -> TaskImportance:
        """Ensure importance is valid enum value."""
        if isinstance(v, TaskImportance):
            return v
        try:
            return TaskImportance(v)
        except ValueError:
            return TaskImportance.NORMAL
    
    @computed_field
    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status == TaskStatus.COMPLETED or self.completed_date_time is not None
    
    @computed_field
    @property
    def is_in_focus(self) -> bool:
        """Check if task should be in focus (not completed, high importance or urgent)."""
        if self.is_completed:
            return False
        if self.importance == TaskImportance.HIGH or self.is_important:
            return True
        # Check if overdue
        if self.due_date_time:
            try:
                due = self.due_date_time.date_time
                if isinstance(due, str):
                    due = datetime.fromisoformat(due.replace('Z', '+00:00'))
                return due < datetime.now(due.tzinfo if due.tzinfo else None)
            except (ValueError, TypeError, AttributeError):
                pass
        return False
    
    @computed_field
    @property
    def completed_at(self) -> datetime | None:
        """Get completion timestamp if available."""
        if not self.completed_date_time:
            return None
        try:
            dt = self.completed_date_time.date_time
            if isinstance(dt, str):
                return datetime.fromisoformat(dt.replace('Z', '+00:00'))
            return dt
        except (ValueError, TypeError, AttributeError):
            return None


class TodoList(BaseModel):
    """Todo task list/container."""
    id: str
    display_name: str = Field(alias="displayName", default="Tasks")
    is_owner: bool = Field(alias="isOwner", default=True)
    wellknown_list_name: str | None = Field(alias="wellknownListName", default=None)
    tasks: list[TodoTask] = Field(default_factory=list)
