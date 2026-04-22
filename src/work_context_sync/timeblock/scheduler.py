"""Aggressive scheduling strategy - maximize scheduled time with tight packing."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, time, date
from typing import List, Optional, Tuple
from dataclasses import dataclass

from .models import Task, TaskCategory, TimeSlot, TimeBlock, ScheduleConstraints

logger = logging.getLogger("work_context_sync.timeblock.scheduler")


@dataclass
class ScheduleContext:
    """Context for scheduling a single day."""
    target_date: date
    tasks: List[Task]
    existing_calendar: List[TimeBlock]  # Already scheduled meetings
    constraints: ScheduleConstraints
    user_patterns: Optional[dict] = None


class AggressiveScheduler:
    """
    Aggressive time-blocking strategy:
    - 5-minute buffers (not 15)
    - Schedule everything with priority >= 0.5
    - 25-minute minimum, no maximum
    - Pack admin tasks into small gaps
    - Minimize fragmentation
    """
    
    def __init__(self, constraints: Optional[ScheduleConstraints] = None):
        self.constraints = constraints or ScheduleConstraints()
        self.buffer = timedelta(minutes=5)
        self.min_priority_threshold = 0.5
    
    def schedule(self, context: ScheduleContext) -> Tuple[List[TimeBlock], List[Task]]:
        """
        Main scheduling algorithm.
        
        Returns:
            (scheduled_blocks, unscheduled_tasks)
        """
        logger.info(
            f"Starting aggressive schedule for {context.target_date} "
            f"with {len(context.tasks)} tasks"
        )
        
        # 1. Get free time slots
        free_slots = self._get_free_slots(context)
        logger.debug(f"Found {len(free_slots)} free slots totaling {self._total_minutes(free_slots)} min")
        
        # 2. Filter and sort tasks by priority
        eligible_tasks = [
            t for t in context.tasks 
            if t.priority >= self.min_priority_threshold
        ]
        
        if not eligible_tasks:
            logger.info("No eligible tasks (all below priority threshold)")
            return [], context.tasks
        
        # Sort: higher priority first, then category alignment
        sorted_tasks = self._sort_tasks_by_priority(eligible_tasks)
        
        # 3. Greedy bin-packing
        scheduled = []
        unscheduled = []
        
        for task in sorted_tasks:
            # Check safety limits
            if len(scheduled) >= self.constraints.max_blocks_per_day:
                logger.warning(f"Reached max blocks limit ({self.constraints.max_blocks_per_day})")
                unscheduled.extend(sorted_tasks[len(scheduled):])
                break
            
            # Find best slot
            best_slot, score = self._find_best_slot(task, free_slots)
            
            if best_slot and score > 0.5:
                block = self._create_block(task, best_slot, score)
                scheduled.append(block)
                
                # Update free slots
                free_slots = self._remove_slot_time(free_slots, best_slot, block)
                logger.debug(f"Scheduled '{task.title}' at {block.start.strftime('%H:%M')} (score: {score:.2f})")
            else:
                # Try to find a fragment slot (aggressive fragmentation)
                fragment_block = self._try_fragment_slot(task, free_slots)
                if fragment_block:
                    scheduled.append(fragment_block)
                    free_slots = self._remove_slot_time(free_slots, TimeSlot(fragment_block.start, fragment_block.end), fragment_block)
                    logger.debug(f"Scheduled '{task.title}' in fragment slot at {fragment_block.start.strftime('%H:%M')}")
                else:
                    unscheduled.append(task)
                    logger.debug(f"Could not schedule '{task.title}' - no suitable slot")
        
        # 4. Add buffers and insert breaks
        scheduled = self._insert_buffers(scheduled)
        scheduled = self._ensure_lunch_break(scheduled, context)
        scheduled = self._ensure_min_unstructured_time(scheduled, context)
        
        logger.info(
            f"Schedule complete: {len(scheduled)} blocks, "
            f"{len(unscheduled)} unscheduled, "
            f"{self._total_minutes(free_slots)} min free remaining"
        )
        
        return scheduled, unscheduled
    
    def _get_free_slots(self, context: ScheduleContext) -> List[TimeSlot]:
        """Calculate free time slots for the day."""
        # Build work day boundaries
        tz = context.constraints.work_start.tzinfo
        day_start = datetime.combine(context.target_date, context.constraints.work_start)
        day_end = datetime.combine(context.target_date, context.constraints.work_end)
        
        slots = [TimeSlot(day_start, day_end)]
        
        # Subtract existing calendar events
        for event in context.existing_calendar:
            if event.start and event.end:
                slots = self._subtract_event(slots, event)
        
        # Subtract protected times (lunch, recurring meetings)
        slots = self._subtract_protected_times(slots, context)
        
        # Filter out slots that are too small
        min_slot = self.constraints.min_block_size + self.buffer
        slots = [s for s in slots if s.duration >= min_slot]
        
        return sorted(slots, key=lambda s: s.start)
    
    def _subtract_event(self, slots: List[TimeSlot], event) -> List[TimeSlot]:
        """Remove an event from free slots."""
        result = []
        
        for slot in slots:
            # No overlap
            if event.end <= slot.start or event.start >= slot.end:
                result.append(slot)
                continue
            
            # Event completely covers slot
            if event.start <= slot.start and event.end >= slot.end:
                continue
            
            # Event cuts slot - keep before and/or after
            if event.start > slot.start:
                # Keep time before event
                result.append(TimeSlot(slot.start, event.start))
            
            if event.end < slot.end:
                # Keep time after event
                result.append(TimeSlot(event.end, slot.end))
        
        return result
    
    def _subtract_protected_times(self, slots: List[TimeSlot], context: ScheduleContext) -> List[TimeSlot]:
        """Remove protected times (lunch, recurring meetings)."""
        protected_events = []
        
        # Lunch
        lunch_start = datetime.combine(
            context.target_date, 
            context.constraints.lunch_start
        )
        lunch_end = lunch_start + context.constraints.lunch_duration
        protected_events.append(TimeSlot(lunch_start, lunch_end))
        
        # Protected recurring meetings
        for protected in context.constraints.protected_times:
            if protected.get("day") == context.target_date.strftime("%A"):
                time_str = protected.get("time", "12:00")
                hour, minute = map(int, time_str.split(":"))
                start = datetime.combine(
                    context.target_date,
                    time(hour, minute)
                )
                duration = timedelta(minutes=protected.get("duration_minutes", 60))
                end = start + duration
                protected_events.append(TimeSlot(start, end))
        
        # Subtract each protected time
        for protected in protected_events:
            slots = self._subtract_protected_slot(slots, protected)
        
        return slots
    
    def _subtract_protected_slot(self, slots: List[TimeSlot], protected: TimeSlot) -> List[TimeSlot]:
        """Remove protected slot with buffer."""
        # Add buffer before and after protected time
        buffered_start = protected.start - self.buffer
        buffered_end = protected.end + self.buffer
        buffered = TimeSlot(buffered_start, buffered_end)
        
        result = []
        for slot in slots:
            if buffered.end <= slot.start or buffered.start >= slot.end:
                result.append(slot)
                continue
            
            if buffered.start > slot.start:
                result.append(TimeSlot(slot.start, buffered.start))
            
            if buffered.end < slot.end:
                result.append(TimeSlot(buffered_end, slot.end))
        
        return result
    
    def _sort_tasks_by_priority(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks: higher priority first, then category energy alignment."""
        def sort_key(task):
            # Primary: priority
            priority_score = task.priority
            
            # Secondary: category alignment with morning hours (9-11am)
            alignment_boost = 0
            if task.category == TaskCategory.DEEP_WORK:
                alignment_boost = 0.1  # Prefer morning for deep work
            elif task.category == TaskCategory.ADMIN:
                alignment_boost = 0.05  # Admin can go anywhere
            
            # Tertiary: due today gets boost
            due_boost = 0.2 if task.is_due_today else 0
            
            return -(priority_score + alignment_boost + due_boost)
        
        return sorted(tasks, key=sort_key)
    
    def _find_best_slot(self, task: Task, slots: List[TimeSlot]) -> Tuple[Optional[TimeSlot], float]:
        """Find the best slot for a task, return (slot, score)."""
        best_slot = None
        best_score = 0.0
        
        for slot in slots:
            if slot.duration < task.estimated_duration:
                continue
            
            score = self._score_slot_for_task(slot, task)
            
            if score > best_score:
                best_score = score
                best_slot = slot
        
        return best_slot, best_score
    
    def _score_slot_for_task(self, slot: TimeSlot, task: Task) -> float:
        """Calculate fitness score 0.0-1.0 for placing task in slot."""
        score = 1.0
        
        # Duration fit (prefer tight fits to minimize fragmentation)
        wasted = slot.duration - task.estimated_duration
        if wasted > timedelta(minutes=30):
            score *= 0.8  # Penalize large gaps
        elif wasted < timedelta(minutes=10):
            score *= 1.1  # Bonus for tight fit
        
        # Hour alignment with category
        hour = slot.start.hour
        preferred_hours = self.constraints.category_fitness.get(task.category, range(8, 18))
        
        if hour in preferred_hours:
            score *= 1.2
        else:
            score *= 0.8
        
        # Time of day decay (later in day = less ideal for deep work)
        if task.category == TaskCategory.DEEP_WORK and hour > 14:
            score *= 0.9
        
        # Urgency boost for same-day scheduling
        if task.is_due_today:
            score *= 1.15
        
        return min(score, 1.0)
    
    def _create_block(self, task: Task, slot: TimeSlot, confidence: float) -> TimeBlock:
        """Create a time block from a slot and task."""
        # Use exact duration, leaving remainder as free time
        end_time = slot.start + task.estimated_duration
        
        return TimeBlock(
            task=task,
            start=slot.start,
            end=end_time,
            confidence=confidence,
            source="aggressive-scheduler"
        )
    
    def _try_fragment_slot(self, task: Task, slots: List[TimeSlot]) -> Optional[TimeBlock]:
        """Aggressive: try to use a fragment of a larger slot."""
        # For admin tasks, accept smaller slots
        if task.category == TaskCategory.ADMIN:
            for slot in slots:
                if timedelta(minutes=15) <= slot.duration < task.estimated_duration:
                    return TimeBlock(
                        task=task,
                        start=slot.start,
                        end=slot.end,  # Use all available
                        confidence=0.5,  # Lower confidence
                        source="fragment-scheduler"
                    )
        
        return None
    
    def _remove_slot_time(self, slots: List[TimeSlot], used_slot: TimeSlot, block: TimeBlock) -> List[TimeSlot]:
        """Remove used time from free slots."""
        result = []
        
        for slot in slots:
            # No overlap
            if used_slot.end <= slot.start or used_slot.start >= slot.end:
                result.append(slot)
                continue
            
            # Block with buffer
            block_end_with_buffer = block.end + self.buffer
            
            if block.start > slot.start:
                # Keep time before block
                result.append(TimeSlot(slot.start, block.start))
            
            if block_end_with_buffer < slot.end:
                # Keep time after block + buffer
                result.append(TimeSlot(block_end_with_buffer, slot.end))
        
        return result
    
    def _insert_buffers(self, blocks: List[TimeBlock]) -> List[TimeBlock]:
        """Insert 5-minute buffers between blocks (already handled in slot removal)."""
        return blocks
    
    def _ensure_lunch_break(self, blocks: List[TimeBlock], context: ScheduleContext) -> List[TimeBlock]:
        """Ensure lunch slot is preserved (already in protected times)."""
        return blocks
    
    def _ensure_min_unstructured_time(self, blocks: List[TimeBlock], context: ScheduleContext) -> List[TimeBlock]:
        """Ensure at least 60 min of unstructured time."""
        total_scheduled = sum(b.duration for b in blocks, timedelta())
        
        work_day_minutes = (
            datetime.combine(context.target_date, context.constraints.work_end) -
            datetime.combine(context.target_date, context.constraints.work_start)
        ).total_seconds() / 60
        
        unstructured = work_day_minutes - (total_scheduled.total_seconds() / 60)
        
        if unstructured < context.constraints.min_unstructured_minutes:
            logger.warning(
                f"Only {unstructured:.0f} min unstructured time (min: {context.constraints.min_unstructured_minutes})"
            )
            # Consider removing lowest-priority buffer blocks
            blocks = self._trim_lowest_priority_blocks(blocks)
        
        return blocks
    
    def _trim_lowest_priority_blocks(self, blocks: List[TimeBlock]) -> List[TimeBlock]:
        """Remove lowest priority blocks if over-scheduled."""
        # Sort by priority (keep high priority)
        sorted_blocks = sorted(blocks, key=lambda b: b.task.priority if b.task else 0)
        
        # Remove lowest priority until we have unstructured time
        # (This is a safety valve, shouldn't happen often)
        return sorted_blocks[len(sorted_blocks) // 2:]  # Keep top half
    
    def _total_minutes(self, slots: List[TimeSlot]) -> int:
        """Total minutes in slots."""
        return int(sum(s.duration.total_seconds() for s in slots) / 60)
