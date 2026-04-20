from __future__ import annotations

import logging
from datetime import date

from .auth import GraphAuthSession
from .graph_client import GraphClient
from .models.exceptions import SyncSourceError
from .sources.calendar import fetch_calendar_items
from .sources.mail import fetch_mail_items
from .sources.todo import fetch_todo_items
from .sources.teams_meetings import fetch_teams_meeting_items
from .sources.teams_chats import fetch_teams_chat_items
from .writers.raw_writer import write_raw_outputs
from .writers.markdown_writer import write_markdown_output

logger = logging.getLogger("work_context_sync.pipeline")


SOURCE_FETCHERS = {
    "calendar": fetch_calendar_items,
    "mail": fetch_mail_items,
    "todo": fetch_todo_items,
    "teams_meetings": fetch_teams_meeting_items,
    "teams_chats": fetch_teams_chat_items,
}


def run_sync(config, target_date: date, selected_sources: list[str] | None = None) -> None:
    selected = set(selected_sources or ["calendar", "mail", "todo"])
    
    logger.info("Starting sync for %s with sources: %s", target_date.isoformat(), ", ".join(sorted(selected)))

    auth_session = GraphAuthSession(config)
    graph_client = GraphClient(config=config, auth_session=auth_session)

    result = {name: None for name in SOURCE_FETCHERS}
    errors: list[SyncSourceError] = []

    for source_name, fetcher in SOURCE_FETCHERS.items():
        if source_name not in selected:
            continue
        try:
            result[source_name] = fetcher(graph_client, target_date)
            logger.info("Synced %s for %s", source_name, target_date.isoformat())
        except Exception as exc:
            error = SyncSourceError(source_name, exc, target_date=target_date.isoformat())
            errors.append(error)
            result[source_name] = {
                "value": [],
                "error": str(exc),
            }
            logger.error("Failed to sync %s for %s: %s", source_name, target_date.isoformat(), exc)

    # Write outputs even if some sources failed
    write_raw_outputs(config=config, target_date=target_date, result=result)
    write_markdown_output(config=config, target_date=target_date, result=result)
    
    # Log summary
    success_count = len(selected) - len(errors)
    if errors:
        logger.warning("Sync completed with %d/%d sources successful", success_count, len(selected))
        for err in errors:
            logger.debug("Error detail: %s", err)
    else:
        logger.info("Sync completed successfully for all %d sources", len(selected))
