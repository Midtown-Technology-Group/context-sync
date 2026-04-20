from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..models.calendar import CalendarEvent, CalendarResult


def fetch_calendar_items(graph_client, target_date: date) -> dict:
    """Fetch calendar events for target date.
    
    Returns dict for backward compatibility with writers.
    Uses CalendarEvent model for validation and computed properties.
    """
    tz = ZoneInfo(graph_client.config.timezone)
    start = datetime.combine(target_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    params = {
        "startDateTime": start.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "id,subject,start,end,organizer,attendees,location,isOnlineMeeting,categories,responseStatus,isCancelled,webLink",
        "$top": graph_client.config.graph.max_page_size,
        "$orderby": "start/dateTime",
    }
    raw_response = graph_client.get_all("/me/calendarView", params=params)
    
    # Validate and transform events
    events_data = raw_response.get("value", [])
    validated_events = []
    for event_data in events_data:
        try:
            event = CalendarEvent.model_validate(event_data)
            validated_events.append(event)
        except Exception:
            # Skip invalid events but log could be added here
            continue
    
    # Return dict for backward compatibility (JSON mode for datetime serialization)
    return {
        "value": [event.model_dump(by_alias=True, mode="json") for event in validated_events]
    }
