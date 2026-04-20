from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from ..models.mail import MailMessage


def fetch_mail_items(graph_client, target_date: date) -> dict:
    """Fetch sent mail items for target date.
    
    Returns dict for backward compatibility with writers.
    Uses MailMessage model for validation and computed properties.
    """
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    params = {
        "$select": "id,subject,sentDateTime,receivedDateTime,from,toRecipients,ccRecipients,categories,conversationId,parentFolderId,importance,webLink,flag",
        "$top": min(graph_client.config.mail.max_items, graph_client.config.graph.max_page_size),
        "$filter": f"sentDateTime ge {start.isoformat()} and sentDateTime lt {end.isoformat()}",
        "$orderby": "sentDateTime asc",
    }
    raw_response = graph_client.get_all("/me/mailFolders/sentitems/messages", params=params)
    
    # Validate and transform messages
    messages_data = raw_response.get("value", [])
    validated_messages = []
    for message_data in messages_data:
        try:
            message = MailMessage.model_validate(message_data)
            validated_messages.append(message)
        except Exception:
            # Skip invalid messages
            continue
    
    # Return dict for backward compatibility (JSON mode for datetime serialization)
    return {
        "value": [msg.model_dump(by_alias=True, mode="json") for msg in validated_messages]
    }
