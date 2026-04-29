"""Meta-test: logs/ directory is git-ignored so per-run log files do not
pollute git status. v1.3.0 introduces logs/ as an on-disk artifact."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
GITIGNORE = REPO_ROOT / ".gitignore"


def test_logs_directory_is_git_ignored() -> None:
    text = GITIGNORE.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    assert "logs/" in lines or "logs" in lines or "logs/*" in lines, (
        ".gitignore must contain a 'logs/' entry so per-run log files written by "
        "core/logging.py do not show up in `git status`."
    )
