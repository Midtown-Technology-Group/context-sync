from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone


def fetch_mail_items(graph_client, target_date: date) -> dict:
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    params = {
        "$select": "id,subject,sentDateTime,receivedDateTime,from,toRecipients,ccRecipients,categories,conversationId,parentFolderId,importance,webLink,flag",
        "$top": min(graph_client.config.mail.max_items, graph_client.config.graph.max_page_size),
        "$filter": f"sentDateTime ge {start.isoformat()} and sentDateTime lt {end.isoformat()}",
        "$orderby": "sentDateTime asc",
    }
    return graph_client.get_all("/me/mailFolders/sentitems/messages", params=params)
