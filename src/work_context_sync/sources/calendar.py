from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def fetch_calendar_items(graph_client, target_date: date) -> dict:
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
    return graph_client.get_all("/me/calendarView", params=params)
