"""Test utilities and fixtures for work-context-sync.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, Mock

import pytest

from work_context_sync.models import (
    AppConfig,
    AuthConfig,
    GraphConfig,
    MailConfig,
    OutputConfig,
)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_config(temp_dir: Path) -> AppConfig:
    """Create a valid mock configuration for testing."""
    config = AppConfig(
        tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
        client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
        vault_path=temp_dir,
        timezone="America/New_York",
        mail=MailConfig(
            include_sent=True,
            include_flagged=True,
            selected_folders=["sentitems"],
            max_items=100,
        ),
        output=OutputConfig(
            write_raw_json=True,
            write_markdown=True,
        ),
        graph=GraphConfig(
            max_page_size=100,
            chat_message_limit_per_chat=25,
            request_retry_count=4,
            request_retry_base_seconds=2,
        ),
        auth=AuthConfig(
            mode="device-code",
            prefer_azure_cli=False,
            allow_broker=False,
        ),
        token_cache_path=str(temp_dir / "token_cache.bin"),
    )
    return config


@pytest.fixture
def mock_graph_response() -> dict:
    """Sample Graph API response for calendar events."""
    return {
        "value": [
            {
                "id": "event-1",
                "subject": "Test Meeting",
                "start": {
                    "dateTime": "2026-04-20T09:00:00.0000000",
                    "timeZone": "America/New_York",
                },
                "end": {
                    "dateTime": "2026-04-20T09:30:00.0000000",
                    "timeZone": "America/New_York",
                },
                "organizer": {
                    "emailAddress": {
                        "name": "Test Organizer",
                        "address": "organizer@example.com",
                    }
                },
                "isOnlineMeeting": False,
                "isCancelled": False,
            }
        ]
    }


@pytest.fixture
def mock_auth_session() -> MagicMock:
    """Mock authentication session that returns a test token."""
    mock = MagicMock()
    mock.acquire_token.return_value = "test-access-token"
    return mock
