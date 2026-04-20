from __future__ import annotations

from datetime import date

from ..models.todo import TodoTask


def _is_completed_on_target(task: TodoTask, target_date: date) -> bool:
    """Check if task was completed on target date using typed model."""
    if not task.completed_at:
        return False
    return task.completed_at.date() == target_date


def _is_due_on_target(task: TodoTask, target_date: date) -> bool:
    """Check if task is due on target date using typed model."""
    if not task.due_date_time:
        return False
    try:
        due = task.due_date_time.date_time
        if isinstance(due, str):
            from datetime import datetime
            due = datetime.fromisoformat(due.replace('Z', '+00:00'))
        return due.date() == target_date
    except (ValueError, TypeError, AttributeError):
        return False


def fetch_todo_items(graph_client, target_date: date) -> dict:
    """Fetch todo items for target date.
    
    Returns dict for backward compatibility with writers.
    Uses TodoTask model for validation and computed properties.
    """
    lists = graph_client.get_all("/me/todo/lists")
    items = []
    completed_today = []
    open_in_focus = []

    for todo_list in lists.get("value", []):
        list_id = todo_list["id"]
        list_name = todo_list.get("displayName", "(unnamed list)")
        
        tasks = graph_client.get_all(
            f"/me/todo/lists/{list_id}/tasks",
            params={
                "$top": graph_client.config.graph.max_page_size,
            },
        )
        task_items = tasks.get("value", [])
        
        # Validate tasks
        validated_tasks = []
        for task_data in task_items:
            try:
                task = TodoTask.model_validate({**task_data, "list_name": list_name})
                validated_tasks.append(task)
            except Exception:
                continue
        
        items.append({
            "list": todo_list,
            "tasks": [t.model_dump(by_alias=True, mode="json") for t in validated_tasks]
        })

        for task in validated_tasks:
            if _is_completed_on_target(task, target_date):
                completed_today.append(task.model_dump(by_alias=True, mode="json"))
            elif not task.is_completed and (
                task.importance.value == "high" or _is_due_on_target(task, target_date)
            ):
                open_in_focus.append(task.model_dump(by_alias=True, mode="json"))

    return {
        "value": items,
        "completedToday": completed_today,
        "openInFocus": open_in_focus,
    }
