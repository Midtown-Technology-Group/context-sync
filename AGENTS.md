# Context Sync agent guidance

This Python package synchronizes Microsoft 365 context into a LogSeq graph and also includes calendar timeblocking. `src/work_context_sync/` owns Graph/auth clients, sync pipelines, source adapters, data models, Markdown/raw writers, and timeblock scheduling. Read the affected module and [SECURITY.md](SECURITY.md) before changing permissions or data handling.

## Verification and boundaries

Python 3.10+ and development extras are declared in `pyproject.toml`: install with `python -m pip install -e ".[dev]"`. Pytest is configured for `tests/`; `python -m pytest` is a configuration-backed local check, not a claimed CI gate. Packaging and deployment workflows are separate; inspect their exact source/tag contract before release work.

Use mock Graph responses and a disposable graph for tests. Sync writes Markdown and optional raw-response sidecars; preserve graph structure, filenames, dates/timezones, and existing human-authored content. Do not test against a personal/customer graph without the task's explicit target and scope. Keep `config.json`, token caches, mailbox/chat content, and logs out of commits and evidence artifacts.

## Important documentation discrepancy

`SECURITY.md` says no write permissions are required, but `timeblock/calendar_writer.py` creates, moves, marks, and deletes Exchange events. Treat timeblocking as a live write operation. Verify actual requested scopes and command behavior in source; the security page is not proof that every command is read-only. Calendar mutations need a reviewed plan, exact calendar/time window, and independent readback; never run them merely to validate guidance.

Use least-privilege auth and preserve encrypted-cache behavior where configured; never share token caches across users or bypass TLS validation. Read `packaging/PACKAGING-README.md`, Azure Function setup, and deployment scripts only for their respective lanes. MSI install/uninstall changes machine state and requires the authorized environment.

## Secret gate before publication

Before publishing the current PR branch, commit the complete candidate and run
`python3 -I scripts/secret_gate.py --base refs/remotes/origin/main` (native Windows: `python -I`). Require exit 0;
missing tooling/authentication, scan errors and skipped scans block publication.
Then run the existing repository gates. Repeat after changing outgoing commits.
Push exactly the scanned HEAD. This PR scan covers the current branch against its
fetched intended base; other refs, multi-ref pushes and rewritten history require
`--pre-push` with Git's complete ref-update stream. Stop if any pushed ref is
uncovered. See [secret scanning](SECRET-SCANNING.md) for base selection, new branches,
pre-push input and prerequisites. Preserve GitGuardian App, CI and Gitleaks checks.

For a non-default PR target, fetch its destination and pass that exact ref to
`--base`; the remote default is not a substitute for a release/maintenance base.

The secret gate requires Python 3.11+ and approved ggshield >=1.56.1,<2.

Explicit bases require fully qualified refs such as `refs/remotes/origin/main`
or full commit SHAs; ambiguous short names block with exit 20.
