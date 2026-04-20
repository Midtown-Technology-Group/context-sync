"""Work Context Sync - Microsoft 365 to LogSeq integration.

Syncs calendar, email, tasks, and Teams data to your knowledge graph.
"""
from __future__ import annotations

__version__ = "1.1.0"

from .app import main
from .config import load_config
from .models import (
    AppConfig,
    AuthMode,
    CalendarEvent,
    MailMessage,
    SourceType,
    TodoTask,
)
from .pipeline import run_sync

__all__ = [
    "__version__",
    "main",
    "load_config",
    "run_sync",
    "AppConfig",
    "AuthMode",
    "CalendarEvent",
    "MailMessage",
    "SourceType",
    "TodoTask",
]
