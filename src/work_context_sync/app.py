from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta

from .config import load_config
from .pipeline import run_sync
from .utils.logging_config import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync work context into the vault")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    parser.add_argument("--quiet", "-q", action="store_true", help="Enable WARNING-only logging")
    parser.add_argument("--log-file", help="Write logs to file path")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Sync a single day of work context")
    sync_parser.add_argument("target_date", nargs="?", default="today", help="Date in YYYY-MM-DD format or 'today'")
    sync_parser.add_argument("--config", default="config.json", help="Path to config file")
    sync_parser.add_argument("--sources", nargs="*", choices=["calendar", "mail", "todo", "teams_meetings", "teams_chats"], help="Optional subset of sources")

    range_parser = subparsers.add_parser("sync-range", help="Sync a date range of work context")
    range_parser.add_argument("start_date", help="Start date in YYYY-MM-DD format")
    range_parser.add_argument("end_date", help="End date in YYYY-MM-DD format")
    range_parser.add_argument("--config", default="config.json", help="Path to config file")
    range_parser.add_argument("--sources", nargs="*", choices=["calendar", "mail", "todo", "teams_meetings", "teams_chats"], help="Optional subset of sources")

    return parser


def parse_target_date(value: str) -> date:
    if value == "today":
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    
    # Determine log level from flags
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    
    # Setup logging
    log_file = None
    if args.log_file:
        from pathlib import Path
        log_file = Path(args.log_file)
    
    setup_logging(level=log_level, log_file=log_file)
    
    config = load_config(args.config)

    if args.command == "sync":
        target = parse_target_date(args.target_date)
        run_sync(config=config, target_date=target, selected_sources=args.sources)
        return

    if args.command == "sync-range":
        start = parse_target_date(args.start_date)
        end = parse_target_date(args.end_date)
        if end < start:
            raise ValueError("end_date must be on or after start_date")
        for target in iter_date_range(start, end):
            run_sync(config=config, target_date=target, selected_sources=args.sources)


if __name__ == "__main__":
    main()
