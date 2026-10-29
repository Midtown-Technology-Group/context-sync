"""Offline regressions for the async source adapters."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from work_context_sync.async_pipeline import (
    fetch_calendar_items_async,
    fetch_mail_items_async,
    fetch_todo_items_async,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "payload", "expected_id"),
    [
        (fetch_calendar_items_async, {"value": [{"id": "event-1"}]}, "event-1"),
        (fetch_mail_items_async, {"value": [{"id": "mail-1"}]}, "mail-1"),
        (fetch_todo_items_async, {"value": []}, None),
    ],
)
async def test_async_source_model_imports(mock_config, fetcher, payload, expected_id):
    client = SimpleNamespace(config=mock_config, get_all=AsyncMock(return_value=payload))

    result = await fetcher(client, date(2026, 10, 29))

    if expected_id is None:
        assert result == {"value": [], "completedToday": [], "openInFocus": []}
    else:
        assert result["value"][0]["id"] == expected_id
    client.get_all.assert_awaited_once()
