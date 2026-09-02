from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from work_context_sync.commands.timeblock import _resolve_logseq_daily_note


def test_resolve_logseq_daily_note_prefers_underscore_journal(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    canonical = daily_dir / "2026_04_27.md"
    canonical.write_text("- human note\n", encoding="utf-8")

    config = SimpleNamespace(vault_path=str(tmp_path))

    assert _resolve_logseq_daily_note(config, date(2026, 4, 27)) == canonical


def test_resolve_logseq_daily_note_never_targets_hyphenated_duplicate(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    legacy = daily_dir / "2026-04-27.md"
    legacy.write_text("## generated duplicate\n", encoding="utf-8")

    config = SimpleNamespace(vault_path=str(tmp_path))

    assert _resolve_logseq_daily_note(config, date(2026, 4, 27)) == (
        daily_dir / "2026_04_27.md"
    )
