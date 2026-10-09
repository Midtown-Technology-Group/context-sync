from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from work_context_sync.writers import markdown_writer as writer


def test_flagged_and_important_mail_reuse_exact_rendered_lines(tmp_path):
    config = SimpleNamespace(
        output=SimpleNamespace(write_markdown=True), vault_path=tmp_path, timezone="UTC"
    )
    rows = [
        {"subject": "ordinary", "sentDateTime": "2026-10-06T12:30:00Z"},
        {"subject": "flagged café", "flag": {"flagStatus": "flagged"}},
        {"subject": "important", "importance": "high"},
        {"subject": "both", "importance": "high", "flag": {"flagStatus": "flagged"}},
    ]
    with patch.object(writer, "_format_mail_line", wraps=writer._format_mail_line) as formatter:
        writer.write_markdown_output(config, date(2026, 10, 6), {"mail": {"value": rows}})
        assert formatter.call_count == len(rows)
    text = (tmp_path / "pages/work-context___2026-10-06.md").read_text()
    sent, flagged = text.split("## Flagged / Important Email", 1)
    assert "- 12:30 ordinary" in sent
    assert "ordinary" not in flagged
    assert flagged.index("flagged café") < flagged.index("important") < flagged.index("both")
    assert text.count("- both") == 2
