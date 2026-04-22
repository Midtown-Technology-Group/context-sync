"""TimeBlock data models for scheduling and tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time, date
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


class TaskCategory(Enum):
    """Categories for time-blocking optimization."""
    DEEP_WORK = "deep_work"      # Coding, complex analysis
    ADMIN = "admin"              # Email, quick tasks
    MEETINGS = "meetings"        # External commitments
    FOCUS_BLOCK = "focus_block"  # Review, planning
    BUFFER = "buffer"            # Catch-up, overflow
    BREAK = "break"              # Lunch, recharge


class TaskSource(Enum):
    """Where the task originated."""
    TODO = "todo"
    MAIL = "mail"
    PLANNER = "planner"  # Microsoft Planner (project tasks)
    HALO = "halo"  # Future: PSA integration
    HABIT = "habit"
    RECURRING = "recurring"


class BlockOutcome(Enum):
    """What actually happened to a scheduled block."""
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"
    MISSED = "missed"
    DELETED = "deleted"
    IN_PROGRESS = "in_progress"


@dataclass
class Task:
    """A unit of work to be scheduled."""
    id: str
    title: str
    source_type: TaskSource
    category: TaskCategory
    priority: float  # 0.0-1.0
    estimated_duration: timedelta
    
    # Optional
    due_date: Optional[date] = None
    is_due_today: bool = False
    external_link: Optional[str] = None
    notes: Optional[str] = None
    
    # Scheduling metadata
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_count: int = 0
    completed_count: int = 0
    
    def __post_init__(self):
        if self.is_due_today and not self.due_date:
            self.due_date = date.today()


@dataclass 
class TimeSlot:
    """A free period available for scheduling."""
    start: datetime
    end: datetime
    
    @property
    def duration(self) -> timedelta:
        return self.end - self.start
    
    def contains(self, dt: datetime) -> bool:
        return self.start <= dt < self.end
    
    def overlaps(self, other: TimeSlot) -> bool:
        return self.start < other.end and other.start < self.end


@dataclass
class TimeBlock:
    """A scheduled block of time for a specific task."""
    id: str = field(default_factory=lambda: str(uuid4()))
    task: Optional[Task] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    confidence: float = 0.0  # 0.0-1.0 fitness score
    source: str = "unknown"
    
    # Exchange tracking
    event_id: Optional[str] = None  # Exchange event ID
    extended_props: Dict[str, Any] = field(default_factory=dict)
    
    # Outcome tracking
    outcome: Optional[BlockOutcome] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    reschedule_count: int = 0
    
    @property
    def duration(self) -> timedelta:
        if self.start and self.end:
            return self.end - self.start
        return timedelta()
    
    @property
    def title(self) -> str:
        if self.task:
            return self.task.title
        return "Free Block"
    
    def to_exchange_event(self, timezone: str) -> Dict[str, Any]:
        """Convert to Exchange event payload."""
        emoji_map = {
            TaskCategory.DEEP_WORK: "🎯",
            TaskCategory.ADMIN: "📧",
            TaskCategory.MEETINGS: "🤝",
            TaskCategory.FOCUS_BLOCK: "📋",
            TaskCategory.BUFFER: "📝",
            TaskCategory.BREAK: "🍽️",
        }
        
        subject = f"{emoji_map.get(self.task.category, '⏰')} {self.task.title}"
        
        return {
            "subject": subject,
            "body": {
                "contentType": "text",
                "content": f"""Auto-scheduled by context-sync timeblock

Task: {self.task.title}
Category: {self.task.category.value}
Source: {self.task.source_type.value}
Priority: {self.task.priority:.0%}
Confidence: {self.confidence:.0%}
TimeBlock ID: {self.id}

Mark complete in To Do or reply "done" to Teams notification.
"""
            },
            "start": {
                "dateTime": self.start.isoformat() if self.start else None,
                "timeZone": timezone
            },
            "end": {
                "dateTime": self.end.isoformat() if self.end else None,
                "timeZone": timezone
            },
            "categories": ["TimeBlock", self.task.category.value],
            "showAs": "busy",
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 5,
        }


@dataclass
class ScheduleConstraints:
    """User's scheduling preferences and constraints."""
    work_start: time = time(8, 0)
    work_end: time = time(17, 30)
    lunch_start: time = time(12, 0)
    lunch_duration: timedelta = field(default_factory=lambda: timedelta(minutes=30))
    
    min_block_size: timedelta = field(default_factory=lambda: timedelta(minutes=25))
    max_block_size: timedelta = field(default_factory=lambda: timedelta(minutes=120))
    buffer_between: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    
    # Category preferences (hour -> fitness multiplier)
    category_fitness: Dict[TaskCategory, List[int]] = field(default_factory=lambda: {
        TaskCategory.DEEP_WORK: [8, 9, 10, 14, 15],  # High-energy hours
        TaskCategory.ADMIN: [11, 12, 16, 17],        # Low-energy
        TaskCategory.FOCUS_BLOCK: [13, 15, 16],
        TaskCategory.MEETINGS: [9, 10, 14, 15],      # Standard meeting hours
    })
    
    # Protected times (never auto-rebalance these)
    protected_times: List[Dict[str, Any]] = field(default_factory=lambda: [
        {
            "name": "All-Staff Meeting",
            "day": "Wednesday",
            "time": "15:00",
            "duration_minutes": 60,
            "never_auto_rebalance": True
        }
    ])
    
    # Rebalance thresholds
    rebalance_min_meeting_minutes: int = 30
    protected_buffer_minutes: int = 15
    
    # Safety limits
    max_blocks_per_day: int = 12
    max_reschedules_per_day: int = 5
    min_unstructured_minutes: int = 60


@dataclass
class ScheduleRecommendation:
    """Output of the scheduling algorithm."""
    date: date
    blocks: List[TimeBlock] = field(default_factory=list)
    unscheduled_tasks: List[Task] = field(default_factory=list)
    free_slots_remaining: List[TimeSlot] = field(default_factory=list)
    
    # Metadata
    strategy_used: str = "unknown"
    total_scheduled_minutes: int = 0
    total_free_minutes: int = 0
    confidence_score: float = 0.0
    
    def to_markdown(self) -> str:
        """Generate markdown summary for daily note."""
        lines = [
            "## ⏰ TimeBlock Schedule",
            "",
            f"**Strategy:** {self.strategy_used} | **Confidence:** {self.confidence_score:.0%}",
            f"**Scheduled:** {self.total_scheduled_minutes} min | **Free:** {self.total_free_minutes} min",
            "",
            "| Time | Activity | Category | Confidence |",
            "|------|----------|----------|------------|",
        ]
        
        for block in sorted(self.blocks, key=lambda b: b.start or datetime.min):
            time_str = f"{block.start.strftime('%H:%M')}-{block.end.strftime('%H:%M')}"
            cat_emoji = {
                TaskCategory.DEEP_WORK: "🎯",
                TaskCategory.ADMIN: "📧",
                TaskCategory.MEETINGS: "🤝",
                TaskCategory.FOCUS_BLOCK: "📋",
                TaskCategory.BUFFER: "📝",
            }.get(block.task.category, "⏰")
            
            lines.append(
                f"| {time_str} | {block.task.title} | {cat_emoji} {block.task.category.value} | {block.confidence:.0%} |"
            )
        
        if self.unscheduled_tasks:
            lines.extend([
                "",
                "**Unscheduled (no slots available):**",
            ])
            for task in self.unscheduled_tasks:
                lines.append(f"- [ ] {task.title} ({task.estimated_duration.total_seconds() // 60} min)")
        
        lines.append("")
        return "\n".join(lines)


@dataclass
class UserPatterns:
    """Learned user behavior patterns."""
    # Completion rates by hour and category
    completion_by_hour: Dict[int, Dict[TaskCategory, List[bool]]] = field(default_factory=dict)
    
    # Average actual duration vs. estimated
    avg_duration_by_category: Dict[TaskCategory, List[float]] = field(default_factory=dict)
    
    # Reschedule frequency by task type
    reschedule_rate_by_source: Dict[TaskSource, float] = field(default_factory=dict)
    
    # Preferred work hours (learned, not configured)
    actual_work_start: Optional[time] = None
    actual_work_end: Optional[time] = None
    
    # Auto-detected recurring meetings
    detected_recurring: List[Dict[str, Any]] = field(default_factory=list)
