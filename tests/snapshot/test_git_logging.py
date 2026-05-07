"""v1.5 — snapshot/git.git_show emits one DEBUG record on success.

Uses a real tiny git repo (matches the existing test_git.py fixture)
to exercise the subprocess shellout end-to-end. Test discipline (per
spec §8): assert level + extras presence; never full message wording."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from aa_auto_sdr.snapshot.git import git_show


@pytest.fixture(autouse=True)
def _attach_caplog_to_package_logger(caplog):
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    saved_propagate = pkg.propagate
    pkg.addHandler(caplog.handler)
    pkg.setLevel(logging.DEBUG)
    pkg.propagate = False
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)
        pkg.propagate = saved_propagate


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed file (mirrors test_git.py)."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    snap = tmp_path / "snapshots" / "demo.prod" / "2026-04-26T10-00-00+00-00.json"
    snap.parent.mkdir(parents=True)
    snap.write_text('{"schema": "aa-sdr-snapshot/v1", "marker": "v1"}\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_show_emits_debug_with_duration_ms(caplog, tiny_repo: Path):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.snapshot.git")
    git_show(
        ref="HEAD",
        path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
        repo_root=tiny_repo,
    )
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.name == "aa_auto_sdr.snapshot.git"]
    assert len(debugs) == 1
    rec = debugs[0]
    assert isinstance(rec.duration_ms, int)
    assert rec.duration_ms >= 0
