"""Task analyzer: categorizes and prioritizes tasks from various sources."""
from __future__ import annotations

import re
from datetime import timedelta, date
from typing import List, Dict, Any, Optional

from .models import Task, TaskCategory, TaskSource


class TaskAnalyzer:
    """Analyzes raw data from Graph API and converts to categorized tasks."""
    
    # Keywords that trigger category detection
    CATEGORY_KEYWORDS = {
        TaskCategory.DEEP_WORK: [
            "code", "develop", "script", "debug", "analyze", "investigate",
            "sonarqube", "bifrost", "implement", "build", "configure",
            "troubleshoot", "diagnose", "performance", "optimization",
        ],
        TaskCategory.ADMIN: [
            "email", "reply", "respond", "follow up", "follow-up",
            "expense", "invoice", "timesheet", "documentation",
            "update", "review request", "approve", "sign",
        ],
        TaskCategory.MEETINGS: [
            "meeting", "call", "sync", "discussion", "standup",
            "review", "demo", "presentation", "interview",
            "1:1", "one-on-one", "check-in", "touch base",
        ],
        TaskCategory.FOCUS_BLOCK: [
            "plan", "strategy", "review", "assess", "evaluate",
            "roadmap", "architecture", "design", "research",
            "learn", "read", "study", "catch up",
        ],
    }
    
    # Priority boosters
    URGENCY_PATTERNS = [
        (r"urgent|asap|immediately|critical|down|outage", 0.9),
        (r"today|due today|end of day|eod", 0.8),
        (r"tomorrow|due tomorrow|eom|end of week", 0.6),
        (r"block|blocking|preventing", 0.7),
        (r"client|customer|vip|escalation", 0.5),
    ]
    
    def __init__(self):
        self.today = date.today()
    
    def analyze_todo_tasks(self, todo_data: Dict[str, Any]) -> List[Task]:
        """Extract and categorize tasks from To Do data."""
        tasks = []
        
        lists = todo_data.get("value", [])
        for todo_list in lists:
            list_name = todo_list.get("displayName", "Tasks")
            task_items = todo_list.get("tasks", [])
            
            for task_data in task_items:
                # Skip completed
                if task_data.get("is_completed"):
                    continue
                
                title = task_data.get("title", "")
                if not title:
                    continue
                
                # Determine category from title
                category = self._categorize_by_title(title)
                
                # Calculate priority
                priority = self._calculate_priority(
                    title=title,
                    importance=task_data.get("importance", "normal"),
                    is_focus=task_data.get("is_in_focus", False),
                    due_date_str=task_data.get("dueDateTime"),
                    categories=task_data.get("categories", [])
                )
                
                # Estimate duration based on title patterns
                duration = self._estimate_duration(title, category)
                
                task = Task(
                    id=task_data.get("id", ""),
                    title=title,
                    source_type=TaskSource.TODO,
                    category=category,
                    priority=priority,
                    estimated_duration=duration,
                    due_date=self._parse_due_date(task_data.get("dueDateTime")),
                    is_due_today=self._is_due_today(task_data.get("dueDateTime")),
                    notes=task_data.get("body", {}).get("content", "")[:200],
                )
                tasks.append(task)
        
        return tasks
    
    def analyze_flagged_emails(self, mail_data: Dict[str, Any]) -> List[Task]:
        """Convert flagged/important emails to tasks."""
        tasks = []
        
        emails = mail_data.get("value", [])
        for email in emails:
            # Only flagged or high importance
            is_flagged = (email.get("flag") or {}).get("flagStatus") == "flagged"
            is_important = email.get("importance") == "high"
            
            if not (is_flagged or is_important):
                continue
            
            subject = email.get("subject", "")
            if not subject:
                continue
            
            # Flagged emails are typically admin/reply tasks
            category = TaskCategory.ADMIN
            
            # But check if it's actually something else
            if any(kw in subject.lower() for kw in ["meeting", "sync", "call"]):
                category = TaskCategory.MEETINGS
            elif any(kw in subject.lower() for kw in ["review", "assess", "plan"]):
                category = TaskCategory.FOCUS_BLOCK
            
            priority = 0.6 if is_flagged else 0.7  # High importance gets boost
            if is_flagged and is_important:
                priority = 0.85
            
            # Estimate: email replies usually 15-30 min
            duration = timedelta(minutes=20)
            
            task = Task(
                id=email.get("id", ""),
                title=f"Reply: {subject[:60]}{'...' if len(subject) > 60 else ''}",
                source_type=TaskSource.MAIL,
                category=category,
                priority=priority,
                estimated_duration=duration,
                external_link=email.get("webLink"),
            )
            tasks.append(task)
        
        return tasks
    
    def _categorize_by_title(self, title: str) -> TaskCategory:
        """Determine task category from title keywords."""
        title_lower = title.lower()
        
        scores = {cat: 0 for cat in TaskCategory}
        
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in title_lower:
                    scores[category] += 1
        
        # Return category with highest score, default to FOCUS_BLOCK
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        
        return TaskCategory.FOCUS_BLOCK
    
    def _calculate_priority(
        self,
        title: str,
        importance: str,
        is_focus: bool,
        due_date_str: Optional[str],
        categories: List[str]
    ) -> float:
        """Calculate priority score 0.0-1.0."""
        score = 0.5  # Base priority
        
        # Importance boost
        if importance == "high":
            score += 0.15
        
        # In-focus boost
        if is_focus:
            score += 0.2
        
        # Due date boost
        if due_date_str:
            due = self._parse_due_date(due_date_str)
            if due:
                days_until = (due - self.today).days
                if days_until <= 0:
                    score += 0.25  # Due today or overdue
                elif days_until == 1:
                    score += 0.15  # Due tomorrow
                elif days_until <= 3:
                    score += 0.1
        
        # Keyword urgency boost
        title_lower = title.lower()
        for pattern, boost in self.URGENCY_PATTERNS:
            if re.search(pattern, title_lower):
                score += boost
                break  # Only apply strongest match
        
        # Category-based adjustments
        if any(cat in title_lower for cat in ["security", "backup", "compliance"]):
            score += 0.1
        
        return min(score, 1.0)
    
    def _estimate_duration(self, title: str, category: TaskCategory) -> timedelta:
        """Estimate task duration based on title and category."""
        title_lower = title.lower()
        
        # Check for explicit time mentions
        time_patterns = [
            r'(\d+)\s*min',
            r'(\d+)\s*minute',
            r'(\d+)\s*hr',
            r'(\d+)\s*hour',
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, title_lower)
            if match:
                value = int(match.group(1))
                if 'hr' in title_lower or 'hour' in title_lower:
                    return timedelta(hours=value)
                else:
                    return timedelta(minutes=value)
        
        # Category-based defaults
        defaults = {
            TaskCategory.DEEP_WORK: timedelta(minutes=90),
            TaskCategory.ADMIN: timedelta(minutes=20),
            TaskCategory.MEETINGS: timedelta(minutes=60),
            TaskCategory.FOCUS_BLOCK: timedelta(minutes=45),
            TaskCategory.BUFFER: timedelta(minutes=30),
        }
        
        return defaults.get(category, timedelta(minutes=45))
    
    def _parse_due_date(self, due_date_str: Optional[str]) -> Optional[date]:
        """Parse due date from ISO string."""
        if not due_date_str:
            return None
        
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            return dt.date()
        except (ValueError, TypeError):
            return None
    
    def _is_due_today(self, due_date_str: Optional[str]) -> bool:
        """Check if task is due today."""
        due = self._parse_due_date(due_date_str)
        if due:
            return due <= self.today
        return False
