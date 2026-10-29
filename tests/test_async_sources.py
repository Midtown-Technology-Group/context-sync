"""Offline regressions for the async source adapters."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from work_context_sync.async_pipeline import (
    fetch_calendar_items_async,
    fetch_mail_items_async,
    fetch_todo_items_async,
)
from work_context_sync.sources.todo import fetch_todo_items


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "task_groups",
    [
        [[], []],
        [[{"id": "task-1", "title": "Focus", "importance": "high"}], []],
        [[], [{"id": "task-2", "title": "Later"}]],
        [
            [{"id": "task-1", "title": "Focus", "importance": "high"}],
            [{"id": "task-2", "title": "Later"}, {"title": "Invalid, no ID"}],
        ],
    ],
)
async def test_async_todo_preserves_lists_like_sync(mock_config, task_groups):
    lists = [
        {"id": "list-1", "displayName": "Work", "wellknownListName": "none"},
        {"id": "list-2", "displayName": "Personal", "isOwner": True},
    ]
    responses = {"/me/todo/lists": {"value": lists}}
    for todo_list, tasks in zip(lists, task_groups):
        responses[f"/me/todo/lists/{todo_list['id']}/tasks"] = {"value": tasks}

    def get_all(path, params=None):
        return responses[path]

    sync_client = SimpleNamespace(config=mock_config, get_all=Mock(side_effect=get_all))
    async_client = SimpleNamespace(config=mock_config, get_all=AsyncMock(side_effect=get_all))
    target = date(2026, 10, 29)

    actual = await fetch_todo_items_async(async_client, target)

    assert actual == fetch_todo_items(sync_client, target)
    assert [entry["list"] for entry in actual["value"]] == lists
    assert async_client.get_all.await_count == 3
