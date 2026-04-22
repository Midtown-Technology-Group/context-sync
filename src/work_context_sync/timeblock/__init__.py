"""TimeBlock module - intelligent time blocking for work context."""
from .models import (
    Task, TaskCategory, TaskSource, TimeSlot, TimeBlock,
    BlockOutcome, ScheduleConstraints, ScheduleRecommendation,
    UserPatterns
)
from .analyzer import TaskAnalyzer
from .scheduler import AggressiveScheduler, ScheduleContext
from .calendar_writer import CalendarWriter
from .rebalance_engine import RebalanceEngine, RebalanceResult
from .learning_tracker import LearningTracker

__all__ = [
    # Models
    "Task", "TaskCategory", "TaskSource", "TimeSlot", "TimeBlock",
    "BlockOutcome", "ScheduleConstraints", "ScheduleRecommendation",
    "UserPatterns",
    # Core components
    "TaskAnalyzer",
    "AggressiveScheduler", "ScheduleContext",
    "CalendarWriter",
    "RebalanceEngine", "RebalanceResult",
    "LearningTracker",
]
