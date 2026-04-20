"""Mail message models for Microsoft Graph API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from .base import BaseSourceModel


class FlagStatus(BaseModel):
    """Email flag status."""
    flag_status: str = Field(alias="flagStatus", default="notFlagged")


class MailMessage(BaseSourceModel):
    """Microsoft Graph mail message.
    
    Provides validators for importance and flagged status.
    """
    id: str
    subject: str = "(no subject)"
    sender: dict[str, Any] | None = None
    from_: dict[str, Any] | None = Field(alias="from", default=None)
    to_recipients: list[dict[str, Any]] = Field(alias="toRecipients", default_factory=list)
    received_date_time: datetime | str | None = Field(alias="receivedDateTime", default=None)
    sent_date_time: datetime | str | None = Field(alias="sentDateTime", default=None)
    importance: str = "normal"  # low, normal, high
    is_read: bool = Field(alias="isRead", default=True)
    is_draft: bool = Field(alias="isDraft", default=False)
    flag: FlagStatus = Field(default_factory=FlagStatus)
    body_preview: str = Field(alias="bodyPreview", default="")
    internet_message_id: str | None = Field(alias="internetMessageId", default=None)
    conversation_id: str | None = Field(alias="conversationId", default=None)
    
    @field_validator("importance")
    @classmethod
    def validate_importance(cls, v: str) -> str:
        """Ensure importance is one of allowed values."""
        allowed = {"low", "normal", "high"}
        if v not in allowed:
            return "normal"  # Default fallback
        return v
    
    @field_validator("received_date_time", "sent_date_time", mode="before")
    @classmethod
    def parse_datetime(cls, v: datetime | str | None) -> datetime | str | None:
        """Parse ISO datetime strings if needed."""
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return v  # Keep as string if parse fails
        return v
    
    @computed_field
    @property
    def is_flagged(self) -> bool:
        """Check if message is flagged."""
        return self.flag.flag_status == "flagged" if self.flag else False
    
    @computed_field
    @property
    def is_important(self) -> bool:
        """Check if message has high importance."""
        return self.importance == "high"
    
    @computed_field
    @property
    def sender_name(self) -> str:
        """Extract sender display name."""
        sender = self.from_ or self.sender
        if not sender:
            return ""
        email = sender.get("emailAddress", {})
        return email.get("name") or email.get("address") or ""
    
    @computed_field
    @property
    def to_summary(self) -> str:
        """Summarize To recipients (first 3)."""
        if not self.to_recipients:
            return ""
        names = []
        for recipient in self.to_recipients[:3]:
            email = recipient.get("emailAddress", {})
            name = email.get("name") or email.get("address") or ""
            if name:
                names.append(name)
        result = ", ".join(names)
        if len(self.to_recipients) > 3:
            result += f" +{len(self.to_recipients) - 3} more"
        return result
