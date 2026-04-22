"""Planner integration - sync Microsoft Planner tasks with timeblock."""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import List, Dict, Optional

from ..graph_client import GraphClient
from ..timeblock.models import Task, TaskCategory, TaskSource

logger = logging.getLogger("work_context_sync.sources.planner")


class PlannerSource:
    """
    Fetch tasks from Microsoft Planner.
    
    Planner tasks are project-oriented (different from personal To Do tasks).
    They have:
    - Plans (projects)
    - Buckets (stages/status)
    - Tasks with assignments, due dates, labels
    """
    
    def __init__(self, graph_client: GraphClient):
        self.client = graph_client
    
    def fetch_planner_tasks(self, target_date: date) -> List[Task]:
        """
        Fetch active Planner tasks assigned to the user.
        
        Returns:
            List of Task objects for timeblock scheduling
        """
        tasks = []
        
        try:
            # Step 1: Get all plans the user has access to
            plans = self._get_user_plans()
            logger.info(f"Found {len(plans)} Planner plans")
            
            for plan in plans:
                plan_id = plan.get("id")
                plan_title = plan.get("title", "Unknown Plan")
                
                # Step 2: Get tasks in this plan
                plan_tasks = self._get_plan_tasks(plan_id)
                
                for task_data in plan_tasks:
                    # Skip completed tasks
                    if task_data.get("percentComplete") == 100:
                        continue
                    
                    # Check if task is assigned to current user
                    if not self._is_assigned_to_me(task_data):
                        continue
                    
                    # Convert to Task
                    task = self._convert_to_task(task_data, plan_title)
                    if task:
                        tasks.append(task)
            
            logger.info(f"Fetched {len(tasks)} active Planner tasks")
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to fetch Planner tasks: {e}", exc_info=True)
            return []
    
    def _get_user_plans(self) -> List[Dict]:
        """Get all Planner plans the user can access."""
        try:
            # Get plans via the user's planner membership
            # This gets plans from all groups the user is in
            response = self.client.get_all("/me/planner/plans")
            return response.get("value", [])
        except Exception as e:
            logger.error(f"Failed to get user plans: {e}")
            return []
    
    def _get_plan_tasks(self, plan_id: str) -> List[Dict]:
        """Get all tasks in a specific plan."""
        try:
            response = self.client.get_all(f"/planner/plans/{plan_id}/tasks")
            return response.get("value", [])
        except Exception as e:
            logger.error(f"Failed to get tasks for plan {plan_id}: {e}")
            return []
    
    def _is_assigned_to_me(self, task_data: Dict) -> bool:
        """Check if the current user is assigned to this task."""
        assignments = task_data.get("assignments", {})
        
        # Get current user's ID
        try:
            me = self.client.get("/me")
            my_id = me.get("id")
            
            # Check if my ID is in assignments
            return my_id in assignments
        except Exception:
            # If we can't determine, include the task (better to over-schedule)
            return True
    
    def _convert_to_task(self, task_data: Dict, plan_title: str) -> Optional[Task]:
        """Convert Planner task to timeblock Task."""
        try:
            title = task_data.get("title", "")
            if not title:
                return None
            
            # Determine category from labels or content
            category = self._categorize_planner_task(task_data, plan_title)
            
            # Calculate priority
            priority = self._calculate_priority(task_data)
            
            # Estimate duration
            estimated_minutes = self._estimate_duration(task_data)
            
            # Parse due date
            due_date = None
            is_due_today = False
            if task_data.get("dueDateTime"):
                try:
                    due = datetime.fromisoformat(
                        task_data["dueDateTime"].replace('Z', '+00:00')
                    )
                    due_date = due.date()
                    is_due_today = due_date <= date.today()
                except (ValueError, AttributeError):
                    pass
            
            # Build rich title with plan context
            full_title = f"[{plan_title}] {title}"
            
            # Add bucket/context if available
            bucket_id = task_data.get("bucketId")
            if bucket_id:
                # Could fetch bucket name for more context
                pass
            
            task = Task(
                id=task_data.get("id", ""),
                title=full_title,
                source_type=TaskSource.PLANNER,
                category=category,
                priority=priority,
                estimated_minutes=estimated_minutes,
                due_date=due_date,
                is_due_today=is_due_today,
                external_link=f"https://tasks.office.com/{{tenant}}/Home/Plan/{task_data.get('planId')}/Task/{task_data.get('id')}",
                notes=task_data.get("description", "")[:200] if task_data.get("description") else None,
                plan_id=task_data.get("planId"),
                bucket_id=bucket_id,
                percent_complete=task_data.get("percentComplete", 0),
            )
            
            return task
            
        except Exception as e:
            logger.error(f"Failed to convert Planner task: {e}")
            return None
    
    def _categorize_planner_task(self, task_data: Dict, plan_title: str) -> TaskCategory:
        """Categorize Planner task based on applied labels and content."""
        # Check applied labels
        applied_labels = task_data.get("appliedCategories", {})
        
        # Common Planner label mappings (customizable per org)
        label_category_map = {
            "category1": TaskCategory.DEEP_WORK,   # Often used for development
            "category2": TaskCategory.MEETINGS,  # Often used for review
            "category3": TaskCategory.ADMIN,     # Often used for documentation
            "category4": TaskCategory.FOCUS_BLOCK, # Often used for planning
            "category5": TaskCategory.MEETINGS,    # Often used for urgent
            "category6": TaskCategory.BUFFER,     # Often used for backlog
        }
        
        for label, category in label_category_map.items():
            if applied_labels.get(label):
                return category
        
        # Infer from task content
        title_lower = task_data.get("title", "").lower()
        
        if any(kw in title_lower for kw in ["review", "assess", "analyze", "investigate"]):
            return TaskCategory.FOCUS_BLOCK
        elif any(kw in title_lower for kw in ["code", "develop", "build", "implement", "script"]):
            return TaskCategory.DEEP_WORK
        elif any(kw in title_lower for kw in ["doc", "document", "update", "maintain"]):
            return TaskCategory.ADMIN
        elif any(kw in title_lower for kw in ["meet", "sync", "discuss", "call"]):
            return TaskCategory.MEETINGS
        
        # Default based on completion %
        if task_data.get("percentComplete", 0) < 25:
            return TaskCategory.FOCUS_BLOCK  # Planning stage
        elif task_data.get("percentComplete", 0) < 75:
            return TaskCategory.DEEP_WORK    # Active work
        else:
            return TaskCategory.ADMIN        # Wrap-up
    
    def _calculate_priority(self, task_data: Dict) -> float:
        """Calculate priority 0.0-1.0 for Planner task."""
        score = 0.5  # Base
        
        # Urgency based on due date
        if task_data.get("dueDateTime"):
            try:
                due = datetime.fromisoformat(
                    task_data["dueDateTime"].replace('Z', '+00:00')
                )
                days_until = (due.date() - date.today()).days
                
                if days_until <= 0:
                    score += 0.3  # Overdue
                elif days_until <= 2:
                    score += 0.2  # Due soon
                elif days_until <= 7:
                    score += 0.1
            except (ValueError, AttributeError):
                pass
        
        # Progress-based priority (urgency to finish)
        progress = task_data.get("percentComplete", 0)
        if progress > 75:
            score += 0.15  # Almost done, finish it
        elif progress < 10 and task_data.get("dueDateTime"):
            score += 0.1  # New but has deadline
        
        # Has checklist items
        checklist = task_data.get("checklistItemCount", 0)
        if checklist > 0:
            completed = task_data.get("activeChecklistItemCount", 0)
            if completed < checklist:
                score += 0.05  # Has incomplete subtasks
        
        return min(score, 1.0)
    
    def _estimate_duration(self, task_data: Dict) -> int:
        """Estimate task duration in minutes."""
        # Check for checklist complexity
        checklist_items = task_data.get("checklistItemCount", 0)
        
        # Base estimates by progress
        progress = task_data.get("percentComplete", 0)
        remaining_factor = (100 - progress) / 100
        
        # Estimate based on task complexity
        if checklist_items >= 5:
            base_minutes = 120  # 2 hours for complex tasks
        elif checklist_items >= 2:
            base_minutes = 60   # 1 hour for medium
        else:
            base_minutes = 45   # 45 min for simple
        
        # Adjust for remaining work
        estimated = int(base_minutes * remaining_factor)
        
        # Minimum 15 minutes
        return max(estimated, 15)
    
    def get_plan_summary(self) -> Dict[str, int]:
        """Get summary of tasks per plan."""
        summary = {}
        
        try:
            plans = self._get_user_plans()
            for plan in plans:
                plan_id = plan.get("id")
                plan_title = plan.get("title", "Unknown")
                
                tasks = self._get_plan_tasks(plan_id)
                active_tasks = [
                    t for t in tasks 
                    if t.get("percentComplete", 0) < 100 and self._is_assigned_to_me(t)
                ]
                
                summary[plan_title] = len(active_tasks)
        except Exception as e:
            logger.error(f"Failed to get plan summary: {e}")
        
        return summary
