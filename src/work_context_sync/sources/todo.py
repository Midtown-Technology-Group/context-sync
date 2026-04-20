from __future__ import annotations

from datetime import date


def _is_completed_on_target(task: dict, target_date: date) -> bool:
    completed = (task.get("completedDateTime") or {}).get("dateTime")
    return bool(completed and completed[:10] == target_date.isoformat())


def _is_due_on_target(task: dict, target_date: date) -> bool:
    due = (task.get("dueDateTime") or {}).get("dateTime")
    return bool(due and due[:10] == target_date.isoformat())


def fetch_todo_items(graph_client, target_date: date) -> dict:
    lists = graph_client.get_all("/me/todo/lists")
    items = []
    completed_today = []
    open_in_focus = []

    for todo_list in lists.get("value", []):
        list_id = todo_list["id"]
        tasks = graph_client.get_all(
            f"/me/todo/lists/{list_id}/tasks",
            params={
                "$top": graph_client.config.graph.max_page_size,
            },
        )
        task_items = tasks.get("value", [])
        items.append({
            "list": todo_list,
            "tasks": task_items,
        })

        for task in task_items:
            task_with_list = {
                **task,
                "listName": todo_list.get("displayName", "(unnamed list)"),
            }
            if _is_completed_on_target(task, target_date):
                completed_today.append(task_with_list)
            elif task.get("status") != "completed" and (
                task.get("importance") == "high" or _is_due_on_target(task, target_date)
            ):
                open_in_focus.append(task_with_list)

    return {
        "value": items,
        "completedToday": completed_today,
        "openInFocus": open_in_focus,
    }
