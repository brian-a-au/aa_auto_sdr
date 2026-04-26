"""snapshot/git.py — `git show <ref>:<path>` wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.snapshot.git import git_show


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed file (history of two versions)."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    snap = tmp_path / "snapshots" / "demo.prod" / "2026-04-26T10-00-00+00-00.json"
    snap.parent.mkdir(parents=True)
    snap.write_text('{"schema": "aa-sdr-snapshot/v1", "marker": "v1"}\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=tmp_path, check=True)
    snap.write_text('{"schema": "aa-sdr-snapshot/v1", "marker": "v2"}\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_show_reads_file_at_head(tiny_repo: Path) -> None:
    out = git_show(
        ref="HEAD",
        path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
        repo_root=tiny_repo,
    )
    assert "v2" in out


def test_git_show_reads_file_at_head_minus_one(tiny_repo: Path) -> None:
    out = git_show(
        ref="HEAD~1",
        path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
        repo_root=tiny_repo,
    )
    assert "v1" in out
    assert "v2" not in out


def test_git_show_raises_on_unknown_ref(tiny_repo: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="git show"):
        git_show(
            ref="nonexistent-branch",
            path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
            repo_root=tiny_repo,
        )


def test_git_show_raises_on_unknown_path(tiny_repo: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="git show"):
        git_show(ref="HEAD", path="nope.json", repo_root=tiny_repo)


def test_git_show_raises_outside_repo(tmp_path: Path) -> None:
    """Run against a directory that isn't a git repo."""
    with pytest.raises(SnapshotResolveError):
        git_show(ref="HEAD", path="anything.json", repo_root=tmp_path)
