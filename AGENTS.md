# Context Sync agent guidance

This Python package synchronizes Microsoft 365 context into a LogSeq graph and also includes calendar timeblocking. `src/work_context_sync/` owns Graph/auth clients, sync pipelines, source adapters, data models, Markdown/raw writers, and timeblock scheduling. Read the affected module and [SECURITY.md](SECURITY.md) before changing permissions or data handling.

## Verification and boundaries

Python 3.10+ and development extras are declared in `pyproject.toml`: install with `python -m pip install -e ".[dev]"`. Pytest is configured for `tests/`; `python -m pytest` is a configuration-backed local check, not a claimed CI gate. Packaging and deployment workflows are separate; inspect their exact source/tag contract before release work.

Use mock Graph responses and a disposable graph for tests. Sync writes Markdown and optional raw-response sidecars; preserve graph structure, filenames, dates/timezones, and existing human-authored content. Do not test against a personal/customer graph without the task's explicit target and scope. Keep `config.json`, token caches, mailbox/chat content, and logs out of commits and evidence artifacts.

## Important documentation discrepancy

`SECURITY.md` says no write permissions are required, but `timeblock/calendar_writer.py` creates, moves, marks, and deletes Exchange events. Treat timeblocking as a live write operation. Verify actual requested scopes and command behavior in source; the security page is not proof that every command is read-only. Calendar mutations need a reviewed plan, exact calendar/time window, and independent readback; never run them merely to validate guidance.

Use least-privilege auth and preserve encrypted-cache behavior where configured; never share token caches across users or bypass TLS validation. Read `packaging/PACKAGING-README.md`, Azure Function setup, and deployment scripts only for their respective lanes. MSI install/uninstall changes machine state and requires the authorized environment.
