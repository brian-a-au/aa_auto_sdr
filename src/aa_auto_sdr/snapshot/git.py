"""`git show <ref>:<path>` wrapper for snapshot resolution.

Subprocess only — we don't want a libgit2 dependency for a single shell-out."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from aa_auto_sdr.core.exceptions import SnapshotResolveError

logger = logging.getLogger(__name__)


def git_show(*, ref: str, path: str, repo_root: Path) -> str:
    """Read `<path>` at git `<ref>` from `repo_root`. Returns file content as string.

    Raises SnapshotResolveError on any non-zero exit (unknown ref, missing path,
    not a git repo). The CLI command will format the message for the user."""
    started = time.monotonic()
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # git not installed
        raise SnapshotResolveError(f"git binary not found: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or "(no stderr)"
        raise SnapshotResolveError(f"git show {ref}:{path} failed: {stderr}")
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.debug(
        "git show duration_ms=%s",
        duration_ms,
        extra={"duration_ms": duration_ms},
    )
    return result.stdout
