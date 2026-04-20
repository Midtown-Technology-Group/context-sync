"""Calendar event models for Microsoft Graph API.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, computed_field

from .base import BaseSourceModel


class DateTimeTimeZone(BaseModel):
    """Graph API date/time with timezone representation."""
    date_time: datetime = Field(alias="dateTime")
    time_zone: str = Field(alias="timeZone")


class EmailAddress(BaseModel):
    """Email address with display name."""
    name: str = ""
    address: str = ""


class Attendee(BaseModel):
    """Calendar event attendee."""
    email_address: EmailAddress = Field(alias="emailAddress", default_factory=EmailAddress)
    type: str = "required"  # required, optional, resource
    status: dict[str, str] = Field(default_factory=dict)


class Location(BaseModel):
    """Event location."""
    display_name: str = Field(alias="displayName", default="")
    location_type: str = Field(alias="locationType", default="default")


class CalendarEvent(BaseSourceModel):
    """Microsoft Graph calendar event.
    
    Provides computed properties for common operations.
    """
    id: str
    subject: str = "(no subject)"
    start: DateTimeTimeZone | None = None
    end: DateTimeTimeZone | None = None
    organizer: dict[str, Any] | None = None
    attendees: list[Attendee] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    is_online_meeting: bool = Field(alias="isOnlineMeeting", default=False)
    is_cancelled: bool = Field(alias="isCancelled", default=False)
    categories: list[str] = Field(default_factory=list)
    response_status: dict[str, str] = Field(alias="responseStatus", default_factory=dict)
    web_link: str | None = Field(alias="webLink", default=None)
    online_meeting: dict[str, Any] | None = Field(alias="onlineMeeting", default=None)
    
    @computed_field
    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        if not self.start or not self.end:
            return 0
        try:
            # Parse ISO datetime strings
            start_dt = self.start.date_time
            end_dt = self.end.date_time
            if isinstance(start_dt, str):
                start_dt = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
            if isinstance(end_dt, str):
                end_dt = datetime.fromisoformat(end_dt.replace('Z', '+00:00'))
            delta = end_dt - start_dt
            return int(delta.total_seconds() / 60)
        except (ValueError, TypeError):
            return 0
    
    @computed_field
    @property
    def organizer_name(self) -> str:
        """Extract organizer display name."""
        if not self.organizer:
            return ""
        email = self.organizer.get("emailAddress", {})
        return email.get("name") or email.get("address") or ""
    
    @computed_field
    @property
    def is_all_day(self) -> bool:
        """Check if this is an all-day event."""
        if not self.start or not self.end:
            return False
        try:
            start_dt = self.start.date_time
            if isinstance(start_dt, str):
                start_dt = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
            return start_dt.hour == 0 and start_dt.minute == 0
        except (ValueError, TypeError):
            return False


class CalendarResult(BaseSourceModel):
    """Container for calendar fetch results."""
    events: list[CalendarEvent] = Field(default_factory=list)
    
    @property
    def value(self) -> list[CalendarEvent]:
        """Alias for events (compatibility)."""
        return self.events
