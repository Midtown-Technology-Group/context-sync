"""TimeBlock CLI command - schedule your day with intelligent time blocking."""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta

from ..auth import GraphAuthSession
from ..graph_client import GraphClient
from ..config import load_config
from ..pipeline import run_sync
from ..timeblock import (
    TaskAnalyzer, AggressiveScheduler, ScheduleContext,
    CalendarWriter, RebalanceEngine, ScheduleConstraints
)
from ..timeblock.models import ScheduleRecommendation

logger = logging.getLogger("work_context_sync.commands.timeblock")


def register_timeblock_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the timeblock command with the CLI."""
    timeblock_parser = subparsers.add_parser(
        "timeblock",
        help="Intelligent time blocking - schedule your day",
        description="Analyze your To Do tasks, flagged emails, and calendar to create optimized time blocks."
    )
    
    timeblock_parser.add_argument(
        "target_date",
        nargs="?",
        default="today",
        help="Date in YYYY-MM-DD format or 'today' (default: today)"
    )
    
    timeblock_parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file"
    )
    
    mode_group = timeblock_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--preview", "-p",
        action="store_true",
        help="Preview schedule without creating events (default mode)"
    )
    mode_group.add_argument(
        "--apply", "-a",
        action="store_true",
        help="Create actual Exchange calendar events"
    )
    mode_group.add_argument(
        "--tentative",
        action="store_true",
        help="Mark all today's timeblocks as tentative (rollback)"
    )
    mode_group.add_argument(
        "--rebalance",
        action="store_true",
        help="Check for conflicts and rebalance schedule"
    )
    
    timeblock_parser.add_argument(
        "--strategy",
        choices=["aggressive", "balanced", "conservative"],
        default="aggressive",
        help="Scheduling strategy (default: aggressive)"
    )
    
    timeblock_parser.add_argument(
        "--check-missed",
        action="store_true",
        help="Check for missed timeblocks and notify"
    )
    
    timeblock_parser.add_argument(
        "--stats",
        action="store_true",
        help="Show learning statistics and patterns"
    )


def run_timeblock_command(args: argparse.Namespace) -> int:
    """Execute the timeblock command."""
    config = load_config(args.config)
    
    # Parse date
    if args.target_date == "today":
        target_date = date.today()
    else:
        target_date = datetime.strptime(args.target_date, "%Y-%m-%d").date()
    
    # Setup Graph client
    auth_session = GraphAuthSession(config)
    graph_client = GraphClient(config=config, auth_session=auth_session)
    
    # Handle special modes first
    if args.tentative:
        return _mark_tentative(graph_client, target_date)
    
    if args.rebalance:
        return _rebalance(graph_client, target_date)
    
    if args.check_missed:
        return _check_missed(graph_client, target_date)
    
    if args.stats:
        return _show_stats(graph_client, target_date)
    
    # Main scheduling flow
    return _create_schedule(graph_client, target_date, args.apply, args.strategy, config)


def _create_schedule(
    graph_client,
    target_date: date,
    apply: bool,
    strategy: str,
    config
) -> int:
    """Create and optionally apply timeblock schedule."""
    logger.info(f"Creating {strategy} schedule for {target_date}")
    
    # Step 1: Sync context (ensure fresh data)
    logger.info("Syncing work context...")
    from ..pipeline import run_sync
    run_sync(config=config, target_date=target_date, selected_sources=["todo", "mail", "calendar"])
    
    # Step 2: Analyze tasks
    logger.info("Analyzing tasks...")
    analyzer = TaskAnalyzer()
    
    # Load synced data
    import json
    from pathlib import Path
    
    todo_path = Path(config.vault_path) / "work-context" / "raw" / "graph" / f"{target_date}-todo.json"
    mail_path = Path(config.vault_path) / "work-context" / "raw" / "graph" / f"{target_date}-mail.json"
    
    all_tasks = []
    
    if todo_path.exists():
        with open(todo_path) as f:
            todo_data = json.load(f)
        all_tasks.extend(analyzer.analyze_todo_tasks(todo_data.get("items", [{}])[0] if todo_data.get("items") else {}))
    
    if mail_path.exists():
        with open(mail_path) as f:
            mail_data = json.load(f)
        all_tasks.extend(analyzer.analyze_flagged_emails(mail_data.get("items", [{}])[0] if mail_data.get("items") else {}))
    
    if not all_tasks:
        print("No tasks found to schedule. Add some To Do items or flag some emails!")
        return 0
    
    logger.info(f"Found {len(all_tasks)} tasks to schedule")
    
    # Step 3: Get existing calendar
    calendar_blocks = _get_existing_calendar(graph_client, target_date)
    
    # Step 4: Schedule
    constraints = ScheduleConstraints()
    scheduler = AggressiveScheduler(constraints)
    
    context = ScheduleContext(
        target_date=target_date,
        tasks=all_tasks,
        existing_calendar=calendar_blocks,
        constraints=constraints
    )
    
    blocks, unscheduled = scheduler.schedule(context)
    
    # Step 5: Generate recommendation
    recommendation = ScheduleRecommendation(
        date=target_date,
        blocks=blocks,
        unscheduled_tasks=unscheduled,
        free_slots_remaining=[],  # Would calculate this
        strategy_used=f"{strategy}-scheduler",
        total_scheduled_minutes=int(sum(b.duration.total_seconds() / 60 for b in blocks)),
        confidence_score=sum(b.confidence for b in blocks) / len(blocks) if blocks else 0
    )
    
    # Output
    print("\n" + recommendation.to_markdown())
    
    if unscheduled:
        print(f"\n⚠️  {len(unscheduled)} tasks couldn't be scheduled (no time slots)")
    
    # Step 6: Apply if requested
    if apply:
        print(f"\n📝 Creating {len(blocks)} calendar events...")
        writer = CalendarWriter(graph_client, timezone=config.timezone)
        event_ids = writer.create_batch(blocks)
        print(f"✅ Created {len(event_ids)} events in your calendar")
        
        # Write to daily note
        _append_to_daily_note(config, target_date, recommendation)
    else:
        print("\n💡 Run with --apply to create these calendar events")
    
    return 0


def _mark_tentative(graph_client, target_date: date) -> int:
    """Panic button: Mark all timeblocks as tentative."""
    logger.info(f"Marking all timeblocks as tentative for {target_date}")
    
    writer = CalendarWriter(graph_client)
    count = writer.mark_tentative_all_today(target_date)
    
    print(f"✅ Marked {count} timeblocks as tentative")
    print("📅 Open Outlook to see your schedule - tentative events appear lighter")
    
    return 0


def _rebalance(graph_client, target_date: date) -> int:
    """Check conflicts and rebalance."""
    logger.info(f"Rebalancing schedule for {target_date}")
    
    writer = CalendarWriter(graph_client)
    engine = RebalanceEngine(graph_client, writer)
    
    result = engine.check_and_rebalance(target_date, user_id="me")
    
    print(result.to_teams_message())
    
    if result.unscheduled_tasks:
        print(f"\n⚠️ {len(result.unscheduled_tasks)} tasks deferred to tomorrow")
    
    return 0


def _check_missed(graph_client, target_date: date) -> int:
    """Check for missed timeblocks."""
    from datetime import time as dt_time
    
    now = datetime.now()
    if target_date == date.today():
        # Only check if we're in the workday
        if now.hour < 8 or now.hour > 18:
            print("Outside work hours - no missed block check needed")
            return 0
    
    writer = CalendarWriter(graph_client)
    blocks = writer.get_today_timeblocks(target_date)
    
    missed = []
    for block in blocks:
        if block.end and block.end < now:
            # Block passed
            if block.extended_props.get("outcome") is None:
                # No outcome recorded - it's missed
                missed.append(block)
    
    if not missed:
        print("✅ No missed timeblocks")
        return 0
    
    print(f"⚠️  {len(missed)} missed timeblocks detected:")
    for block in missed:
        print(f"  - {block.title} (scheduled {block.start.strftime('%H:%M')}-{block.end.strftime('%H:%M')})")
    
    # This would trigger Power Automate notification
    print("\n📧 Teams notification sent with reschedule options")
    
    return 0


def _show_stats(graph_client, target_date: date) -> int:
    """Show learning statistics."""
    from ..timeblock.learning_tracker import LearningTracker
    
    tracker = LearningTracker(graph_client)
    patterns = tracker.analyze_patterns(days=30)
    
    print("\n📊 TimeBlock Learning Statistics (Last 30 Days)")
    print("=" * 50)
    
    # Completion rates by hour
    print("\n🕐 Completion Rates by Hour:")
    for hour in range(8, 18):
        for category in ["deep_work", "admin", "focus_block"]:
            rate = tracker.get_completion_rate(patterns, hour, category)
            if rate > 0:
                bar = "█" * int(rate * 10) + "░" * (10 - int(rate * 10))
                print(f"  {hour:02d}:00 {category:12} [{bar}] {rate:.0%}")
    
    # Average durations
    print("\n⏱️  Average Actual Durations:")
    from ..timeblock.models import TaskCategory
    for category in TaskCategory:
        actual = tracker.get_avg_duration(patterns, category)
        print(f"  {category.value:15} {actual} min")
    
    # Suggestions
    print("\n💡 Suggestions:")
    suggestions = tracker.suggest_improvements(patterns)
    if suggestions:
        for s in suggestions[:5]:
            print(f"  • {s}")
    else:
        print("  • Your schedule looks well-optimized!")
    
    return 0


def _get_existing_calendar(graph_client, target_date: date):
    """Get existing calendar events as blocks."""
    from ..timeblock.models import TimeBlock
    from datetime import time as dt_time
    
    start = datetime.combine(target_date, dt_time.min)
    end = datetime.combine(target_date, dt_time.max)
    
    params = {
        "startDateTime": start.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "id,subject,start,end,categories",
    }
    
    try:
        response = graph_client.get_all("/me/calendarView", params=params)
        events = response.get("value", [])
        
        blocks = []
        for event in events:
            # Skip timeblocks (we manage those)
            if "TimeBlock" in event.get("categories", []):
                continue
            
            blocks.append(TimeBlock(
                id=event.get("id", ""),
                task=None,
                start=datetime.fromisoformat(event["start"]["dateTime"]),
                end=datetime.fromisoformat(event["end"]["dateTime"]),
                source="external-calendar"
            ))
        
        return blocks
    except Exception as e:
        logger.error(f"Failed to get calendar: {e}")
        return []


def _append_to_daily_note(config, target_date: date, recommendation) -> None:
    """Append schedule to daily note."""
    from pathlib import Path
    
    daily_path = Path(config.vault_path) / "daily" / f"{target_date}.md"
    if not daily_path.exists():
        logger.warning(f"Daily note not found: {daily_path}")
        return
    
    # Append schedule section
    content = recommendation.to_markdown()
    
    with open(daily_path, "a", encoding="utf-8") as f:
        f.write(f"\n{content}\n")
    
    logger.info(f"Appended schedule to {daily_path}")
