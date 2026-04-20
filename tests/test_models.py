"""Tests for Graph API response models.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from work_context_sync.models import (
    CalendarEvent,
    MailMessage,
    TaskImportance,
    TaskStatus,
    TodoTask,
)


class TestCalendarEvent:
    """Test suite for CalendarEvent model."""

    def test_basic_event_creation(self) -> None:
        """Test creating a basic calendar event."""
        event = CalendarEvent(
            id="event-1",
            subject="Team Meeting",
            start={"dateTime": "2026-04-20T09:00:00", "timeZone": "America/New_York"},
            end={"dateTime": "2026-04-20T09:30:00", "timeZone": "America/New_York"},
        )
        assert event.id == "event-1"
        assert event.subject == "Team Meeting"
        assert event.duration_minutes == 30

    def test_all_day_event(self) -> None:
        """Test all-day event detection."""
        event = CalendarEvent(
            id="event-2",
            subject="All Day Event",
            start={"dateTime": "2026-04-20T00:00:00", "timeZone": "America/New_York"},
            end={"dateTime": "2026-04-21T00:00:00", "timeZone": "America/New_York"},
        )
        assert event.is_all_day is True

    def test_organizer_name_extraction(self) -> None:
        """Test organizer name extraction from nested structure."""
        event = CalendarEvent(
            id="event-3",
            subject="Client Call",
            start={"dateTime": "2026-04-20T10:00:00", "timeZone": "UTC"},
            end={"dateTime": "2026-04-20T11:00:00", "timeZone": "UTC"},
            organizer={
                "emailAddress": {
                    "name": "John Doe",
                    "address": "john@example.com",
                }
            },
        )
        assert event.organizer_name == "John Doe"

    def test_organizer_fallback_to_address(self) -> None:
        """Test organizer falls back to email if name missing."""
        event = CalendarEvent(
            id="event-4",
            subject="External Meeting",
            start={"dateTime": "2026-04-20T14:00:00", "timeZone": "UTC"},
            end={"dateTime": "2026-04-20T15:00:00", "timeZone": "UTC"},
            organizer={
                "emailAddress": {
                    "address": "external@example.com",
                }
            },
        )
        assert event.organizer_name == "external@example.com"

    def test_missing_start_end(self) -> None:
        """Test handling of missing start/end times."""
        event = CalendarEvent(
            id="event-5",
            subject="Tentative",
        )
        assert event.duration_minutes == 0
        assert event.is_all_day is False

    def test_default_subject(self) -> None:
        """Test default subject when missing."""
        event = CalendarEvent(
            id="event-6",
            start={"dateTime": "2026-04-20T09:00:00", "timeZone": "UTC"},
            end={"dateTime": "2026-04-20T10:00:00", "timeZone": "UTC"},
        )
        assert event.subject == "(no subject)"


class TestMailMessage:
    """Test suite for MailMessage model."""

    def test_basic_email(self) -> None:
        """Test creating a basic email message."""
        mail = MailMessage(
            id="mail-1",
            subject="Test Email",
            from_={"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
        )
        assert mail.subject == "Test Email"
        assert mail.sender_name == "Sender"

    def test_high_importance(self) -> None:
        """Test high importance detection."""
        mail = MailMessage(
            id="mail-2",
            subject="Urgent",
            importance="high",
        )
        assert mail.is_important is True
        assert mail.importance == "high"

    def test_flagged_email(self) -> None:
        """Test flagged email detection."""
        mail = MailMessage(
            id="mail-3",
            subject="Follow Up",
            flag={"flagStatus": "flagged"},
        )
        assert mail.is_flagged is True

    def test_to_recipients_summary(self) -> None:
        """Test recipient summary generation."""
        mail = MailMessage(
            id="mail-4",
            subject="Group Email",
            toRecipients=[
                {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
                {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
                {"emailAddress": {"name": "Carol", "address": "carol@example.com"}},
                {"emailAddress": {"name": "David", "address": "david@example.com"}},
            ],
        )
        assert "Alice" in mail.to_summary
        assert "Bob" in mail.to_summary
        assert "Carol" in mail.to_summary
        assert "+1 more" in mail.to_summary

    def test_importance_validation(self) -> None:
        """Test that invalid importance values are normalized."""
        mail = MailMessage(
            id="mail-5",
            subject="Test",
            importance="invalid_value",
        )
        assert mail.importance == "normal"  # Falls back to normal

    def test_datetime_parsing(self) -> None:
        """Test ISO datetime string parsing."""
        mail = MailMessage(
            id="mail-6",
            subject="Test",
            receivedDateTime="2026-04-20T14:30:00Z",
        )
        assert isinstance(mail.received_date_time, datetime)


class TestTodoTask:
    """Test suite for TodoTask model."""

    def test_basic_task(self) -> None:
        """Test creating a basic todo task."""
        task = TodoTask(
            id="task-1",
            title="Complete Documentation",
            status=TaskStatus.NOT_STARTED,
        )
        assert task.title == "Complete Documentation"
        assert task.is_completed is False

    def test_completed_task(self) -> None:
        """Test completed task detection."""
        task = TodoTask(
            id="task-2",
            title="Done Task",
            status=TaskStatus.COMPLETED,
            completedDateTime={
                "dateTime": "2026-04-20T10:00:00Z",
                "timeZone": "UTC",
            },
        )
        assert task.is_completed is True
        assert task.completed_at is not None

    def test_high_importance_in_focus(self) -> None:
        """Test that high importance incomplete tasks are in focus."""
        task = TodoTask(
            id="task-3",
            title="Important Task",
            status=TaskStatus.NOT_STARTED,
            importance=TaskImportance.HIGH,
        )
        assert task.is_in_focus is True

    def test_normal_task_not_in_focus(self) -> None:
        """Test that normal tasks are not in focus."""
        task = TodoTask(
            id="task-4",
            title="Regular Task",
            status=TaskStatus.NOT_STARTED,
            importance=TaskImportance.NORMAL,
        )
        assert task.is_in_focus is False

    def test_completed_task_not_in_focus(self) -> None:
        """Test that completed tasks are never in focus."""
        task = TodoTask(
            id="task-5",
            title="Completed",
            status=TaskStatus.COMPLETED,
            importance=TaskImportance.HIGH,
            completedDateTime={
                "dateTime": "2026-04-20T10:00:00Z",
                "timeZone": "UTC",
            },
        )
        assert task.is_completed is True
        assert task.is_in_focus is False

    def test_default_title(self) -> None:
        """Test default title when missing."""
        task = TodoTask(id="task-6")
        assert task.title == "(untitled task)"

    def test_status_enum_validation(self) -> None:
        """Test status enum validation."""
        task = TodoTask(
            id="task-7",
            title="Test",
            status="invalid_status",  # type: ignore
        )
        assert task.status == TaskStatus.NOT_STARTED  # Falls back

    def test_list_name_field(self) -> None:
        """Test that list_name is populated correctly."""
        task = TodoTask(
            id="task-8",
            title="Work Task",
            list_name="Work Projects",
        )
        assert task.list_name == "Work Projects"
