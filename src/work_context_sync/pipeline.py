from __future__ import annotations

from datetime import date

from .auth import GraphAuthSession
from .graph_client import GraphClient
from .sources.calendar import fetch_calendar_items
from .sources.mail import fetch_mail_items
from .sources.todo import fetch_todo_items
from .sources.teams_meetings import fetch_teams_meeting_items
from .sources.teams_chats import fetch_teams_chat_items
from .writers.raw_writer import write_raw_outputs
from .writers.markdown_writer import write_markdown_output


SOURCE_FETCHERS = {
    "calendar": fetch_calendar_items,
    "mail": fetch_mail_items,
    "todo": fetch_todo_items,
    "teams_meetings": fetch_teams_meeting_items,
    "teams_chats": fetch_teams_chat_items,
}


def run_sync(config, target_date: date, selected_sources: list[str] | None = None) -> None:
    selected = set(selected_sources or ["calendar", "mail", "todo"])

    auth_session = GraphAuthSession(config)
    graph_client = GraphClient(config=config, auth_session=auth_session)

    result = {name: None for name in SOURCE_FETCHERS}

    for source_name, fetcher in SOURCE_FETCHERS.items():
        if source_name not in selected:
            continue
        try:
            result[source_name] = fetcher(graph_client, target_date)
            print(f"[{target_date.isoformat()}] synced {source_name}")
        except Exception as exc:  # noqa: BLE001
            result[source_name] = {
                "value": [],
                "error": str(exc),
            }
            print(f"[{target_date.isoformat()}] failed {source_name}: {exc}")

    write_raw_outputs(config=config, target_date=target_date, result=result)
    write_markdown_output(config=config, target_date=target_date, result=result)
