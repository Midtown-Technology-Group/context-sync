"""Rebalance engine - detects conflicts and re-optimizes schedules."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple

from ..graph_client import GraphClient
from .models import TimeBlock, Task, TimeSlot, BlockOutcome
from .scheduler import AggressiveScheduler, ScheduleContext
from .calendar_writer import CalendarWriter
from .learning_tracker import LearningTracker

logger = logging.getLogger("work_context_sync.timeblock.rebalance")


class RebalanceEngine:
    """
    Detects calendar conflicts and rebalances timeblocks.
    
    Hybrid strategy:
    - <3 conflicts: Minimal rebalancing (just move affected blocks)
    - >=3 conflicts: Full rebuild from scratch
    """
    
    def __init__(
        self,
        graph_client: GraphClient,
        calendar_writer: CalendarWriter,
        timezone: str = "America/Indiana/Indianapolis"
    ):
        self.client = graph_client
        self.writer = calendar_writer
        self.timezone = timezone
        self.scheduler = AggressiveScheduler()
        self.learning = LearningTracker(graph_client)
        
        self.conflict_threshold = 3  # Full rebuild at 3+ conflicts
        self.min_meeting_minutes = 30  # Only rebalance for meetings >30 min
    
    def check_and_rebalance(self, target_date: date, user_id: str) -> RebalanceResult:
        """
        Main entry: Check for conflicts and rebalance if needed.
        
        Returns:
            RebalanceResult with details of what changed
        """
        logger.info(f"Checking for conflicts on {target_date}")
        
        # 1. Get current state
        existing_blocks = self.writer.get_today_timeblocks(target_date)
        calendar_events = self._get_calendar_events(target_date)
        
        # 2. Detect conflicts
        conflicts = self._detect_conflicts(existing_blocks, calendar_events)
        
        if not conflicts:
            logger.info("No conflicts detected")
            return RebalanceResult(target_date, changes=[])
        
        logger.info(f"Detected {len(conflicts)} conflicts")
        
        # 3. Choose strategy
        if len(conflicts) < self.conflict_threshold:
            return self._minimal_rebalance(target_date, existing_blocks, conflicts)
        else:
            return self._full_rebuild(target_date, existing_blocks, calendar_events)
    
    def _detect_conflicts(
        self,
        timeblocks: List[TimeBlock],
        calendar_events: List[Dict]
    ) -> List[CalendarConflict]:
        """Find calendar events that conflict with timeblocks."""
        conflicts = []
        
        for event in calendar_events:
            # Skip small meetings
            duration = self._get_event_duration(event)
            if duration < timedelta(minutes=self.min_meeting_minutes):
                continue
            
            # Skip our own timeblocks
            categories = event.get("categories", [])
            if "TimeBlock" in categories:
                continue
            
            event_start = datetime.fromisoformat(event["start"]["dateTime"])
            event_end = datetime.fromisoformat(event["end"]["dateTime"])
            
            # Check overlap with each timeblock
            for block in timeblocks:
                if not (block.start and block.end):
                    continue
                
                # Overlap check
                if event_start < block.end and event_end > block.start:
                    conflicts.append(CalendarConflict(
                        event=event,
                        affected_block=block,
                        overlap_minutes=(min(block.end, event_end) - max(block.start, event_start)).total_seconds() / 60
                    ))
        
        return conflicts
    
    def _minimal_rebalance(
        self,
        target_date: date,
        existing_blocks: List[TimeBlock],
        conflicts: List[CalendarConflict]
    ) -> RebalanceResult:
        """Minimal strategy: Just move the affected blocks."""
        logger.info("Using minimal rebalance strategy")
        
        changes = []
        
        # Get free slots
        free_slots = self._get_free_slots(target_date, existing_blocks)
        
        for conflict in conflicts:
            block = conflict.affected_block
            
            # Find new slot
            best_slot = self._find_alternative_slot(block, free_slots, target_date)
            
            if best_slot:
                # Move the block
                old_start = block.start
                success = self.writer.move_event(
                    block,
                    best_slot.start,
                    best_slot.start + block.duration
                )
                
                if success:
                    changes.append(RebalanceChange(
                        block=block,
                        old_time=old_start,
                        new_time=block.start,
                        reason=f"Conflict with '{conflict.event.get('subject', 'Meeting')}'"
                    ))
                    
                    # Update free slots
                    free_slots = self._remove_slot(free_slots, TimeSlot(block.start, block.end))
                else:
                    logger.error(f"Failed to move block '{block.title}'")
            else:
                # No slot today - defer to tomorrow
                self._defer_to_tomorrow(block)
                changes.append(RebalanceChange(
                    block=block,
                    old_time=block.start,
                    new_time=None,
                    reason=f"No slots available today (conflict with '{conflict.event.get('subject', 'Meeting')}') - deferred to tomorrow"
                ))
        
        return RebalanceResult(target_date, changes=changes)
    
    def _full_rebuild(
        self,
        target_date: date,
        existing_blocks: List[TimeBlock],
        calendar_events: List[Dict]
    ) -> RebalanceResult:
        """Full strategy: Re-optimize entire day from scratch."""
        logger.info("Using full rebuild strategy")
        
        changes = []
        
        # 1. Extract tasks from existing blocks
        tasks = [b.task for b in existing_blocks if b.task]
        
        # 2. Delete all existing timeblock events
        for block in existing_blocks:
            self.writer.delete_event(block)
            changes.append(RebalanceChange(
                block=block,
                old_time=block.start,
                new_time=None,
                reason="Full rebuild - old schedule removed"
            ))
        
        # 3. Get user patterns for optimization
        patterns = self.learning.analyze_patterns(days=14)
        
        # 4. Build new schedule
        context = ScheduleContext(
            target_date=target_date,
            tasks=tasks,
            existing_calendar=[],  # Will be built from calendar_events
            constraints=self.scheduler.constraints,
            user_patterns=patterns
        )
        
        # Convert calendar events to TimeBlock format for constraints
        for event in calendar_events:
            if "TimeBlock" not in event.get("categories", []):
                context.existing_calendar.append(TimeBlock(
                    start=datetime.fromisoformat(event["start"]["dateTime"]),
                    end=datetime.fromisoformat(event["end"]["dateTime"]),
                    task=None,
                    source="external-calendar"
                ))
        
        new_blocks, unscheduled = self.scheduler.schedule(context)
        
        # 5. Create new events
        for block in new_blocks:
            event_id = self.writer.create_timeblock_event(block)
            if event_id:
                changes.append(RebalanceChange(
                    block=block,
                    old_time=None,
                    new_time=block.start,
                    reason="New optimized schedule"
                ))
        
        logger.info(f"Full rebuild complete: {len(new_blocks)} blocks, {len(unscheduled)} unscheduled")
        
        return RebalanceResult(target_date, changes=changes, unscheduled_tasks=unscheduled)
    
    def _get_calendar_events(self, target_date: date) -> List[Dict]:
        """Get all calendar events for the day."""
        from datetime import time as dt_time
        
        start = datetime.combine(target_date, dt_time.min)
        end = datetime.combine(target_date, dt_time.max)
        
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": "id,subject,start,end,categories,organizer",
            "$orderby": "start/dateTime"
        }
        
        try:
            response = self.client.get_all("/me/calendarView", params=params)
            return response.get("value", [])
        except Exception as e:
            logger.error(f"Failed to get calendar events: {e}")
            return []
    
    def _get_event_duration(self, event: Dict) -> timedelta:
        """Calculate event duration."""
        try:
            start = datetime.fromisoformat(event["start"]["dateTime"])
            end = datetime.fromisoformat(event["end"]["dateTime"])
            return end - start
        except (KeyError, ValueError):
            return timedelta()
    
    def _get_free_slots(self, target_date: date, existing_blocks: List[TimeBlock]) -> List[TimeSlot]:
        """Calculate remaining free time slots."""
        from datetime import time as dt_time
        
        # Work day
        start = datetime.combine(target_date, dt_time(8, 0))
        end = datetime.combine(target_date, dt_time(17, 30))
        
        slots = [TimeSlot(start, end)]
        
        # Subtract all calendar events
        calendar = self._get_calendar_events(target_date)
        for event in calendar:
            event_start = datetime.fromisoformat(event["start"]["dateTime"])
            event_end = datetime.fromisoformat(event["end"]["dateTime"])
            slots = self._subtract_time(slots, event_start, event_end)
        
        # Subtract existing timeblocks
        for block in existing_blocks:
            if block.start and block.end:
                slots = self._subtract_time(slots, block.start, block.end)
        
        # Filter small slots
        return [s for s in slots if s.duration >= timedelta(minutes=25)]
    
    def _subtract_time(self, slots: List[TimeSlot], start: datetime, end: datetime) -> List[TimeSlot]:
        """Remove a time period from slots."""
        result = []
        buffer = timedelta(minutes=5)
        
        start_buffered = start - buffer
        end_buffered = end + buffer
        
        for slot in slots:
            if end_buffered <= slot.start or start_buffered >= slot.end:
                result.append(slot)
                continue
            
            if start_buffered > slot.start:
                result.append(TimeSlot(slot.start, start_buffered))
            
            if end_buffered < slot.end:
                result.append(TimeSlot(end_buffered, slot.end))
        
        return result
    
    def _find_alternative_slot(self, block: TimeBlock, free_slots: List[TimeSlot], target_date: date) -> Optional[TimeSlot]:
        """Find best alternative slot for a block."""
        if not block.task:
            return None
        
        for slot in sorted(free_slots, key=lambda s: s.duration, reverse=True):
            if slot.duration >= block.duration:
                return slot
        
        return None
    
    def _remove_slot(self, slots: List[TimeSlot], used: TimeSlot) -> List[TimeSlot]:
        """Remove used time from free slots."""
        return self._subtract_time(slots, used.start, used.end)
    
    def _defer_to_tomorrow(self, block: TimeBlock) -> None:
        """Mark block for tomorrow scheduling."""
        # Update extended props to indicate deferral
        if block.event_id:
            self.writer.update_outcome(block, BlockOutcome.RESCHEDULED)
        
        logger.info(f"Deferred '{block.title}' to tomorrow")


@dataclass
class CalendarConflict:
    """Represents a conflict between calendar event and timeblock."""
    event: Dict
    affected_block: TimeBlock
    overlap_minutes: float


@dataclass
class RebalanceChange:
    """A single change made during rebalancing."""
    block: TimeBlock
    old_time: Optional[datetime]
    new_time: Optional[datetime]
    reason: str


@dataclass
class RebalanceResult:
    """Complete result of a rebalance operation."""
    target_date: date
    changes: List[RebalanceChange]
    unscheduled_tasks: Optional[List[Task]] = None
    
    def to_teams_message(self) -> str:
        """Generate Teams notification message."""
        if not self.changes:
            return "✅ No conflicts detected - schedule unchanged"
        
        lines = [
            f"🔄 Auto-rebalanced {len(self.changes)} blocks for {self.target_date}",
            ""
        ]
        
        for change in self.changes:
            old = change.old_time.strftime('%H:%M') if change.old_time else "unscheduled"
            new = change.new_time.strftime('%H:%M') if change.new_time else "tomorrow"
            
            emoji = "🔄" if change.new_time else "📅"
            lines.append(f"{emoji} **{change.block.title}**")
            lines.append(f"   {old} → {new}")
            lines.append(f"   _{change.reason}_")
            lines.append("")
        
        if self.unscheduled_tasks:
            lines.append(f"📋 {len(self.unscheduled_tasks)} tasks deferred to tomorrow")
        
        return "\n".join(lines)
