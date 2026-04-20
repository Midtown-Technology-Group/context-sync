"""Async pipeline for parallel data fetching.

Replaces sync pipeline.py with async/await for concurrent source fetching.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from .async_graph_client import AsyncGraphClient
from .models.exceptions import SyncSourceError
from .writers.markdown_writer import write_markdown_output
from .writers.raw_writer import write_raw_outputs

logger = logging.getLogger("work_context_sync.async_pipeline")


# Type aliases for source fetcher functions
SourceFetcher = callable


# Registry of async source fetchers
ASYNC_SOURCE_FETCHERS: dict[str, SourceFetcher] = {}


def register_async_fetcher(name: str):
    """Decorator to register an async source fetcher."""
    def decorator(func: SourceFetcher) -> SourceFetcher:
        ASYNC_SOURCE_FETCHERS[name] = func
        return func
    return decorator


@register_async_fetcher("calendar")
async def fetch_calendar_items_async(client: AsyncGraphClient, target_date: date) -> dict:
    """Async fetch calendar events for target date."""
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo
    
    tz = ZoneInfo(client.config.timezone)
    start = datetime.combine(target_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    
    params = {
        "startDateTime": start.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "id,subject,start,end,organizer,attendees,location,isOnlineMeeting,categories,responseStatus,isCancelled,webLink",
        "$top": client.config.graph.max_page_size,
        "$orderby": "start/dateTime",
    }
    
    result = await client.get_all("/me/calendarView", params=params)
    
    # Validate into typed models
    from ..models.calendar import CalendarEvent
    validated = []
    for event_data in result.get("value", []):
        try:
            event = CalendarEvent.model_validate(event_data)
            validated.append(event.model_dump(by_alias=True, mode="json"))
        except Exception:
            continue
    
    return {"value": validated}


@register_async_fetcher("mail")
async def fetch_mail_items_async(client: AsyncGraphClient, target_date: date) -> dict:
    """Async fetch mail items for target date."""
    from datetime import datetime, time, timedelta, timezone
    
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    
    params = {
        "$select": "id,subject,sentDateTime,receivedDateTime,from,toRecipients,ccRecipients,categories,conversationId,parentFolderId,importance,webLink,flag",
        "$top": min(client.config.mail.max_items, client.config.graph.max_page_size),
        "$filter": f"sentDateTime ge {start.isoformat()} and sentDateTime lt {end.isoformat()}",
        "$orderby": "sentDateTime asc",
    }
    
    result = await client.get_all("/me/mailFolders/sentitems/messages", params=params)
    
    # Validate into typed models
    from ..models.mail import MailMessage
    validated = []
    for msg_data in result.get("value", []):
        try:
            msg = MailMessage.model_validate(msg_data)
            validated.append(msg.model_dump(by_alias=True, mode="json"))
        except Exception:
            continue
    
    return {"value": validated}


@register_async_fetcher("todo")
async def fetch_todo_items_async(client: AsyncGraphClient, target_date: date) -> dict:
    """Async fetch todo items for target date."""
    from .sources.todo import _is_completed_on_target, _is_due_on_target
    from ..models.todo import TodoTask
    
    lists = await client.get_all("/me/todo/lists")
    items = []
    completed_today = []
    open_in_focus = []
    
    # Fetch tasks from all lists concurrently
    async def fetch_list_tasks(todo_list: dict) -> tuple:
        list_id = todo_list["id"]
        list_name = todo_list.get("displayName", "(unnamed list)")
        
        tasks = await client.get_all(
            f"/me/todo/lists/{list_id}/tasks",
            params={"$top": client.config.graph.max_page_size},
        )
        return list_name, tasks.get("value", [])
    
    list_tasks = [fetch_list_tasks(tl) for tl in lists.get("value", [])]
    list_results = await asyncio.gather(*list_tasks)
    
    for list_name, task_items in list_results:
        # Validate tasks
        validated = []
        for task_data in task_items:
            try:
                task = TodoTask.model_validate({**task_data, "list_name": list_name})
                validated.append(task)
            except Exception:
                continue
        
        items.append({
            "list": {"id": task_data.get("id", ""), "displayName": list_name},
            "tasks": [t.model_dump(by_alias=True, mode="json") for t in validated]
        })
        
        for task in validated:
            if _is_completed_on_target(task, target_date):
                completed_today.append(task.model_dump(by_alias=True, mode="json"))
            elif not task.is_completed and (task.importance.value == "high" or _is_due_on_target(task, target_date)):
                open_in_focus.append(task.model_dump(by_alias=True, mode="json"))
    
    return {
        "value": items,
        "completedToday": completed_today,
        "openInFocus": open_in_focus,
    }


@register_async_fetcher("teams_meetings")
async def fetch_teams_meetings_async(client: AsyncGraphClient, target_date: date) -> dict:
    """Async fetch Teams meetings for target date."""
    from datetime import datetime, time, timedelta, timezone
    
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    
    params = {
        "$select": "id,subject,start,end,organizer,attendees,isOnlineMeeting,onlineMeeting,onlineMeetingProvider,onlineMeetingUrl",
        "$filter": f"start/dateTime ge '{start.isoformat()}' and start/dateTime lt '{end.isoformat()}'",
        "$orderby": "start/dateTime",
    }
    
    return await client.get_all("/me/calendarView", params=params)


@register_async_fetcher("teams_chats")
async def fetch_teams_chats_async(client: AsyncGraphClient, target_date: date) -> dict:
    """Async fetch Teams chats with recent messages."""
    from datetime import datetime, time, timedelta, timezone
    
    # Get all chats
    chats = await client.get_all("/me/chats")
    
    # Get recent messages for each chat
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    
    async def fetch_chat_messages(chat: dict) -> dict:
        chat_id = chat.get("id")
        if not chat_id:
            return chat
        
        try:
            messages = await client.get_all(
                f"/me/chats/{chat_id}/messages",
                params={
                    "$top": client.config.graph.chat_message_limit_per_chat,
                    "$filter": f"createdDateTime ge {start.isoformat()} and createdDateTime lt {end.isoformat()}",
                    "$orderby": "createdDateTime desc",
                }
            )
            chat["messagesToday"] = messages.get("value", [])
        except Exception:
            chat["messagesToday"] = []
        
        return chat
    
    # Fetch messages for all chats concurrently
    chat_tasks = [fetch_chat_messages(chat) for chat in chats.get("value", [])]
    chats_with_messages = await asyncio.gather(*chat_tasks)
    
    return {"value": chats_with_messages}


async def run_async_sync(
    config, 
    target_date: date, 
    selected_sources: list[str] | None = None
) -> None:
    """Run async sync for selected data sources.
    
    Fetches all sources concurrently using asyncio.gather for maximum
    performance. Writes results to markdown and raw JSON.
    
    Args:
        config: Application configuration
        target_date: Date to sync
        selected_sources: List of source names or None for defaults
    """
    selected = set(selected_sources or ["calendar", "mail", "todo"])
    
    logger.info(
        "Starting async sync for %s with sources: %s", 
        target_date.isoformat(), 
        ", ".join(sorted(selected))
    )
    
    # Import auth here to avoid circular imports
    from .auth import GraphAuthSession
    auth_session = GraphAuthSession(config)
    
    result = {name: None for name in ASYNC_SOURCE_FETCHERS}
    errors: list[SyncSourceError] = []
    
    async with AsyncGraphClient(config, auth_session) as client:
        # Build tasks for selected sources
        tasks = []
        task_names = []
        
        for source_name in ASYNC_SOURCE_FETCHERS:
            if source_name not in selected:
                continue
            fetcher = ASYNC_SOURCE_FETCHERS[source_name]
            tasks.append(fetcher(client, target_date))
            task_names.append(source_name)
        
        # Execute all fetches concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for source_name, res in zip(task_names, results):
                if isinstance(res, Exception):
                    error = SyncSourceError(source_name, res, target_date=target_date.isoformat())
                    errors.append(error)
                    result[source_name] = {"value": [], "error": str(res)}
                    logger.error("Failed to sync %s for %s: %s", source_name, target_date.isoformat(), res)
                else:
                    result[source_name] = res
                    logger.info("Synced %s for %s", source_name, target_date.isoformat())
    
    # Write outputs
    write_raw_outputs(config=config, target_date=target_date, result=result)
    write_markdown_output(config=config, target_date=target_date, result=result)
    
    # Log summary
    success_count = len(selected) - len(errors)
    if errors:
        logger.warning("Async sync completed with %d/%d sources successful", success_count, len(selected))
    else:
        logger.info("Async sync completed successfully for all %d sources", len(selected))
