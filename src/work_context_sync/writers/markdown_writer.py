from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def _format_person(person: dict | None) -> str:
    if not person:
        return ""
    email = (person.get("emailAddress") or {})
    return email.get("name") or email.get("address") or ""


def _convert_to_local(iso_str: str, tz_str: str) -> datetime | None:
    """Convert ISO datetime string to local timezone."""
    if not iso_str:
        return None
    try:
        # Parse the ISO string (Graph API returns ISO 8601 format)
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        # Convert to local timezone
        local_tz = ZoneInfo(tz_str)
        return dt.astimezone(local_tz)
    except Exception:
        return None


def _format_event_line(item: dict, timezone: str) -> str:
    start_iso = (item.get("start") or {}).get("dateTime", "")
    end_iso = (item.get("end") or {}).get("dateTime", "")
    subject = item.get("subject", "(no subject)")
    organizer = _format_person(item.get("organizer"))
    
    # Convert to local timezone
    start_local = _convert_to_local(start_iso, timezone)
    end_local = _convert_to_local(end_iso, timezone)
    
    is_all_day = False
    if start_local and end_local:
        # Check if it's an all-day event (midnight to midnight)
        is_all_day = start_local.hour == 0 and start_local.minute == 0 and \
                     end_local.hour == 0 and end_local.minute == 0 and \
                     (end_local - start_local).seconds >= 86399  # At least 23:59:59
    
    time_part = "All day " if is_all_day else ""
    if start_local and end_local and not is_all_day:
        time_part = f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')} "
    
    organizer_part = f" | organizer: {organizer}" if organizer else ""
    return f"- {time_part}{subject}{organizer_part}"


def _format_mail_line(item: dict, timezone: str) -> str:
    ts_iso = item.get("sentDateTime") or item.get("receivedDateTime") or ""
    subject = item.get("subject", "(no subject)")
    to_recipients = item.get("toRecipients") or []
    to_summary = ", ".join(filter(None, [_format_person(p) for p in to_recipients[:3]]))
    to_part = f" | to: {to_summary}" if to_summary else ""
    
    # Convert to local timezone
    ts_local = _convert_to_local(ts_iso, timezone)
    ts_part = f"{ts_local.strftime('%H:%M')} " if ts_local else ""
    
    return f"- {ts_part}{subject}{to_part}"


def _add_error_section(lines: list[str], result: dict) -> None:
    errors = []
    for source_name, payload in result.items():
        if payload and payload.get("error"):
            errors.append(f"- {source_name}: {payload['error']}")
    if not errors:
        return
    lines.extend(["## Sync issues", *errors, ""])


def write_markdown_output(config, target_date: date, result: dict) -> None:
    if not config.output.write_markdown:
        return

    out_dir = Path(config.vault_path) / "work-context" / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)

    calendar_payload = result.get("calendar") or {}
    mail_payload = result.get("mail") or {}
    todo_payload = result.get("todo") or {}
    teams_meetings_payload = result.get("teams_meetings") or {}
    teams_chats_payload = result.get("teams_chats") or {}

    calendar_items = calendar_payload.get("value", [])
    mail_items = mail_payload.get("value", [])
    todo_lists = todo_payload.get("value", [])
    completed_today = todo_payload.get("completedToday", [])
    open_in_focus = todo_payload.get("openInFocus", [])
    teams_meetings = teams_meetings_payload.get("value", [])
    teams_chats = teams_chats_payload.get("value", [])

    lines = [
        f"# Workday Context — {target_date.isoformat()}",
        "",
        "## Summary",
        f"- Calendar items: {len(calendar_items)}",
        f"- Sent email items: {len(mail_items)}",
        f"- To Do lists synced: {len(todo_lists)}",
        f"- Completed tasks today: {len(completed_today)}",
        f"- Open tasks in focus: {len(open_in_focus)}",
        f"- Teams meetings: {len(teams_meetings)}",
        f"- Teams chats active today: {len(teams_chats)}",
        "",
    ]

    _add_error_section(lines, result)

    tz = config.timezone

    lines.append("## Calendar")
    if calendar_items:
        for item in calendar_items:
            lines.append(_format_event_line(item, tz))
    else:
        lines.append("- ")

    lines.extend(["", "## Teams Meetings"])
    if teams_meetings:
        for item in teams_meetings:
            provider = item.get("onlineMeetingProvider") or "online"
            join_url = item.get("onlineMeetingUrl")
            lines.append(_format_event_line(item, tz) + f" | provider: {provider}")
            if join_url:
                lines.append(f"  - join URL present")
    else:
        lines.append("- ")

    lines.extend(["", "## Teams Chats Active Today"])
    if teams_chats:
        for chat in teams_chats:
            lines.append(f"- {chat.get('topic', '(untitled chat)')} | type: {chat.get('chatType', 'unknown')} | messages: {len(chat.get('messagesToday', []))}")
            for message in chat.get("messagesToday", [])[:3]:
                created = message.get("createdDateTime") or ""
                ts_local = _convert_to_local(created, tz)
                timestamp = ts_local.strftime('%H:%M') if ts_local else ""
                lines.append(f"  - {timestamp} {message.get('sender', 'Unknown')}: {message.get('summary', '')}")
    else:
        lines.append("- ")

    lines.extend(["", "## Sent Email"])
    if mail_items:
        for item in mail_items:
            lines.append(_format_mail_line(item, tz))
    else:
        lines.append("- ")

    flagged_items = [item for item in mail_items if (item.get("flag") or {}).get("flagStatus") == "flagged" or item.get("importance") == "high"]
    lines.extend(["", "## Flagged / Important Email"])
    if flagged_items:
        for item in flagged_items:
            lines.append(_format_mail_line(item, tz))
    else:
        lines.append("- ")

    lines.extend(["", "## To Do", "", "### Completed today"])
    if completed_today:
        for item in completed_today:
            lines.append(f"- [{item.get('listName', '(list)')}] {item.get('title', '(untitled task)')}")
    else:
        lines.append("- ")

    lines.extend(["", "### Open / in focus"])
    if open_in_focus:
        for item in open_in_focus:
            lines.append(f"- [{item.get('listName', '(list)')}] {item.get('title', '(untitled task)')}")
    else:
        lines.append("- ")

    lines.extend([
        "",
        "## Tickets / PSA",
        "- ",
        "",
        "## Candidate work themes",
        "- ",
        "",
        "## Candidate clients / orgs",
        "- ",
        "",
        "## Candidate timesheet blocks",
        "- ",
        "",
        "## Notes for daily note",
        "- ",
    ])

    path = out_dir / f"{target_date.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
