"""Enumerations for type-safe configuration and source names."""
from __future__ import annotations

from enum import StrEnum


class AuthMode(StrEnum):
    """Authentication mode options."""
    WAM = "wam"
    INTERACTIVE = "interactive"
    DEVICE_CODE = "device-code"
    AZURE_CLI = "azure-cli"
    AUTO = "auto"


class SourceType(StrEnum):
    """Data source types for sync."""
    CALENDAR = "calendar"
    MAIL = "mail"
    TODO = "todo"
    TEAMS_MEETINGS = "teams_meetings"
    TEAMS_CHATS = "teams_chats"
