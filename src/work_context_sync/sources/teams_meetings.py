from __future__ import annotations

from datetime import date


def fetch_teams_meeting_items(graph_client, target_date: date) -> dict:
    from .calendar import fetch_calendar_items

    calendar_payload = fetch_calendar_items(graph_client, target_date)
    meetings = []
    for item in calendar_payload.get("value", []):
        if item.get("isOnlineMeeting"):
            meetings.append(item)
    return {"value": meetings}
