"""Learning tracker - analyzes user behavior and adapts scheduling."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, date, time
from typing import Dict, List, Any, Optional
from collections import defaultdict

from ..graph_client import GraphClient
from .models import TaskCategory, TaskSource, BlockOutcome, UserPatterns, TimeBlock

logger = logging.getLogger("work_context_sync.timeblock.learning")


class LearningTracker:
    """
    Tracks what actually happened vs. what was planned.
    Uses Exchange extended properties for storage (no local DB).
    """
    
    EXT_PROP_NAME = "timeblock_meta"
    app_guid = "timeblock-sync-1.0"
    
    def __init__(self, graph_client: GraphClient):
        self.client = graph_client
    
    def analyze_patterns(self, days: int = 30) -> UserPatterns:
        """Analyze last N days of timeblock history."""
        from datetime import time as dt_time
        
        end = datetime.now()
        start = end - timedelta(days=days)
        
        # Query Exchange for past timeblocks
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": "id,subject,start,end,showAs,categories,singleValueExtendedProperties",
            "$expand": f"singleValueExtendedProperties($filter=id eq 'String {{{self.app_guid}}} Name {self.EXT_PROP_NAME}')",
            "$orderby": "start/dateTime",
            "$top": 100
        }
        
        try:
            response = self.client.get_all("/me/calendarView", params=params)
            events = response.get("value", [])
            
            patterns = UserPatterns()
            
            for event in events:
                categories = event.get("categories", [])
                if "TimeBlock" not in categories:
                    continue
                
                props = self._extract_props(event)
                if not props:
                    continue
                
                # Parse timing
                start_dt = datetime.fromisoformat(event["start"]["dateTime"])
                end_dt = datetime.fromisoformat(event["end"]["dateTime"])
                hour = start_dt.hour
                
                # Get category
                category_str = props.get("category", "focus_block")
                try:
                    category = TaskCategory(category_str)
                except ValueError:
                    category = TaskCategory.FOCUS_BLOCK
                
                # Track completion
                outcome_str = props.get("outcome")
                is_completed = outcome_str == "completed"
                
                # Store completion by hour
                if hour not in patterns.completion_by_hour:
                    patterns.completion_by_hour[hour] = defaultdict(list)
                patterns.completion_by_hour[hour][category].append(is_completed)
                
                # Track actual vs estimated duration
                actual_duration = (end_dt - start_dt).total_seconds() / 60
                if category not in patterns.avg_duration_by_category:
                    patterns.avg_duration_by_category[category] = []
                patterns.avg_duration_by_category[category].append(actual_duration)
                
                # Track reschedule rates
                reschedule_count = props.get("reschedule_count", 0)
                source_str = props.get("source_type", "unknown")
                try:
                    source = TaskSource(source_str)
                except ValueError:
                    source = TaskSource.TODO
                
                if source not in patterns.reschedule_rate_by_source:
                    patterns.reschedule_rate_by_source[source] = []
                patterns.reschedule_rate_by_source[source].append(reschedule_count)
            
            # Calculate work hours from data
            all_hours = sorted(patterns.completion_by_hour.keys())
            if all_hours:
                patterns.actual_work_start = time(min(all_hours), 0)
                patterns.actual_work_end = time(max(all_hours) + 1, 0)
            
            logger.info(f"Analyzed {len(events)} timeblocks over {days} days")
            return patterns
            
        except Exception as e:
            logger.error(f"Failed to analyze patterns: {e}")
            return UserPatterns()
    
    def get_completion_rate(self, patterns: UserPatterns, hour: int, category: TaskCategory) -> float:
        """Get completion rate for a specific hour/category."""
        if hour not in patterns.completion_by_hour:
            return 0.5  # Default 50%
        
        results = patterns.completion_by_hour[hour].get(category, [])
        if not results:
            return 0.5
        
        return sum(results) / len(results)
    
    def get_avg_duration(self, patterns: UserPatterns, category: TaskCategory) -> int:
        """Get average actual duration in minutes for a category."""
        durations = patterns.avg_duration_by_category.get(category, [])
        if not durations:
            # Return defaults
            defaults = {
                TaskCategory.DEEP_WORK: 90,
                TaskCategory.ADMIN: 20,
                TaskCategory.MEETINGS: 60,
                TaskCategory.FOCUS_BLOCK: 45,
            }
            return defaults.get(category, 45)
        
        return int(sum(durations) / len(durations))
    
    def get_reschedule_rate(self, patterns: UserPatterns, source: TaskSource) -> float:
        """Get average reschedule count for a source type."""
        counts = patterns.reschedule_rate_by_source.get(source, [])
        if not counts:
            return 0.0
        
        return sum(counts) / len(counts)
    
    def suggest_improvements(self, patterns: UserPatterns) -> List[str]:
        """Generate human-readable suggestions based on patterns."""
        suggestions = []
        
        # Check for low completion hours
        for hour in range(8, 18):
            rate = self.get_completion_rate(patterns, hour, TaskCategory.DEEP_WORK)
            if rate < 0.3:
                suggestions.append(
                    f"⚠️ Deep work scheduled at {hour}:00 has only {rate:.0%} completion rate. "
                    f"Consider moving to {patterns.completion_by_hour.get(hour + 2, {}).get(TaskCategory.DEEP_WORK, 'N/A')}"
                )
        
        # Check for over-scheduling
        if patterns.reschedule_rate_by_source:
            avg_reschedules = sum(
                sum(counts) / len(counts) 
                for counts in patterns.reschedule_rate_by_source.values()
            ) / len(patterns.reschedule_rate_by_source)
            
            if avg_reschedules > 1.5:
                suggestions.append(
                    f"📊 Average {avg_reschedules:.1f} reschedules per task. "
                    f"Consider blocking larger chunks or reducing meeting load."
                )
        
        # Check for duration estimation accuracy
        for category in TaskCategory:
            actual = self.get_avg_duration(patterns, category)
            estimated = {  # Default estimates
                TaskCategory.DEEP_WORK: 90,
                TaskCategory.ADMIN: 20,
                TaskCategory.MEETINGS: 60,
                TaskCategory.FOCUS_BLOCK: 45,
            }.get(category, 45)
            
            diff = abs(actual - estimated)
            if diff > 15:
                suggestions.append(
                    f"🎯 {category.value} tasks take ~{actual} min on average "
                    f"(estimated {estimated} min). Consider adjusting."
                )
        
        return suggestions
    
    def _extract_props(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract extended properties from event."""
        ext_props = event.get("singleValueExtendedProperties", [])
        
        for prop in ext_props:
            if self.EXT_PROP_NAME in prop.get("id", ""):
                try:
                    return json.loads(prop.get("value", "{}"))
                except json.JSONDecodeError:
                    return None
        
        return None
