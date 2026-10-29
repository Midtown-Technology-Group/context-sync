"""Offline regressions for the async source adapters."""

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from work_context_sync.async_pipeline import (
    fetch_calendar_items_async,
    fetch_mail_items_async,
    fetch_todo_items_async,
    run_async_sync,
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


@pytest.mark.asyncio
async def test_async_sync_writes_successful_source_outputs(mock_config):
    responses = {
        "/me/calendarView": {"value": [{"id": "event-1", "subject": "Planning"}]},
        "/me/mailFolders/sentitems/messages": {"value": [{"id": "mail-1", "subject": "Follow up"}]},
        "/me/todo/lists": {"value": [{"id": "list-1", "displayName": "Work"}]},
        "/me/todo/lists/list-1/tasks": {"value": []},
    }
    client = AsyncMock()
    client.config = mock_config
    client.get_all.side_effect = lambda path, params=None: responses[path]
    with (
        patch("work_context_sync.async_pipeline.AsyncGraphClient") as client_class,
        patch("work_context_sync.auth.GraphAuthSession"),
    ):
        client_class.return_value.__aenter__ = AsyncMock(return_value=client)
        client_class.return_value.__aexit__ = AsyncMock(return_value=False)
        await run_async_sync(mock_config, date(2026, 10, 29))

    raw_dir = mock_config.vault_path / "work-context/raw/graph"
    for source in ["calendar", "mail", "todo"]:
        payload = json.loads((raw_dir / f"2026-10-29-{source}.json").read_text())
        assert payload["status"] == "ok"
        assert payload["error"] is None
        assert len(payload["items"]) == 1
        if source == "todo":
            assert payload["items"][0]["list"]["id"] == "list-1"
            assert payload["items"][0]["tasks"] == []
    markdown = (mock_config.vault_path / "pages/work-context___2026-10-29.md").read_text()
    assert "## Sync issues" not in markdown
    assert "Planning" in markdown
    assert "Follow up" in markdown
    assert "To Do lists synced: 1" in markdown
