from __future__ import annotations

from datetime import date
import re


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _message_on_target(message: dict, target_date: date) -> bool:
    created = message.get("createdDateTime") or ""
    return created[:10] == target_date.isoformat()


def _chat_title(chat: dict, members: list[dict]) -> str:
    topic = chat.get("topic")
    if topic:
        return topic
    names = []
    for member in members[:4]:
        display = member.get("displayName")
        if display:
            names.append(display)
    return ", ".join(names) if names else "(untitled chat)"


def fetch_teams_chat_items(graph_client, target_date: date) -> dict:
    chat_top = min(graph_client.config.graph.max_page_size, 50)
    chats = graph_client.get_all(
        "/me/chats",
        params={
            "$top": chat_top,
            "$expand": "lastMessagePreview",
            "$orderby": "lastMessagePreview/createdDateTime desc",
        },
    )

    active_chats = []
    for chat in chats.get("value", []):
        preview = chat.get("lastMessagePreview") or {}
        preview_date = preview.get("createdDateTime") or ""
        if preview_date and preview_date[:10] != target_date.isoformat():
            continue

        chat_id = chat["id"]
        messages_payload = graph_client.get_all(
            f"/chats/{chat_id}/messages",
            params={
                "$top": graph_client.config.graph.chat_message_limit_per_chat,
            },
        )
        messages = messages_payload.get("value", [])
        day_messages = []
        for message in messages:
            if _message_on_target(message, target_date):
                sender = (((message.get("from") or {}).get("user") or {}).get("displayName")) or "Unknown"
                body = _strip_html(((message.get("body") or {}).get("content")) or "")
                day_messages.append(
                    {
                        "id": message.get("id"),
                        "createdDateTime": message.get("createdDateTime"),
                        "sender": sender,
                        "summary": body[:280],
                    }
                )
        if not day_messages:
            continue

        members_payload = graph_client.get_all(f"/chats/{chat_id}/members")
        members = members_payload.get("value", [])
        active_chats.append(
            {
                "id": chat_id,
                "chatType": chat.get("chatType"),
                "topic": _chat_title(chat, members),
                "webUrl": chat.get("webUrl"),
                "messagesToday": day_messages,
                "memberCount": len(members),
            }
        )

    return {"value": active_chats}
