"""snapshot.git write operations — real-git subprocess via tmp_path."""

from __future__ import annotations

import subprocess
from pathlib import Path

from aa_auto_sdr.snapshot.git import (
    git_init_snapshot_repo,
    is_git_repository,
)


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Test helper: run a git command in cwd, return CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


class TestIsGitRepository:
    def test_returns_false_for_non_repo(self, tmp_path: Path) -> None:
        assert is_git_repository(tmp_path) is False

    def test_returns_true_after_git_init(self, tmp_path: Path) -> None:
        _run_git(["init"], tmp_path)
        assert is_git_repository(tmp_path) is True

    def test_returns_false_for_nonexistent_path(self, tmp_path: Path) -> None:
        assert is_git_repository(tmp_path / "does-not-exist") is False


class TestGitInitSnapshotRepo:
    def test_creates_git_dir_and_initial_commit(self, tmp_path: Path) -> None:
        _run_git(["config", "--local", "user.email", "test@example.com"], tmp_path)
        _run_git(["config", "--local", "user.name", "Test User"], tmp_path)
        result = git_init_snapshot_repo(tmp_path)
        assert result.ok is True
        assert result.error_kind is None
        assert (tmp_path / ".git").is_dir()
        assert (tmp_path / "README.md").is_file()
        # Initial commit recorded.
        log = _run_git(["log", "--oneline"], tmp_path)
        assert log.returncode == 0
        assert "Initial commit" in log.stdout

    def test_idempotent_on_existing_repo(self, tmp_path: Path) -> None:
        # First init.
        _run_git(["config", "--local", "user.email", "test@example.com"], tmp_path)
        _run_git(["config", "--local", "user.name", "Test User"], tmp_path)
        git_init_snapshot_repo(tmp_path)
        # Second init: idempotent — returns ok without re-initializing.
        result = git_init_snapshot_repo(tmp_path)
        assert result.ok is True
        # README still intact; only one initial commit.
        log = _run_git(["log", "--oneline"], tmp_path)
        assert log.stdout.count("\n") == 1  # only the initial commit

    def test_sets_commit_gpgsign_false_locally(self, tmp_path: Path) -> None:
        _run_git(["config", "--local", "user.email", "test@example.com"], tmp_path)
        _run_git(["config", "--local", "user.name", "Test User"], tmp_path)
        git_init_snapshot_repo(tmp_path)
        config = _run_git(["config", "--local", "commit.gpgsign"], tmp_path)
        assert config.stdout.strip() == "false"

    def test_initial_branch_is_main(self, tmp_path: Path) -> None:
        _run_git(["config", "--local", "user.email", "test@example.com"], tmp_path)
        _run_git(["config", "--local", "user.name", "Test User"], tmp_path)
        git_init_snapshot_repo(tmp_path)
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], tmp_path)
        assert branch.stdout.strip() == "main"

    def test_readme_identifies_snapshot_store(self, tmp_path: Path) -> None:
        _run_git(["config", "--local", "user.email", "test@example.com"], tmp_path)
        _run_git(["config", "--local", "user.name", "Test User"], tmp_path)
        git_init_snapshot_repo(tmp_path)
        readme = (tmp_path / "README.md").read_text()
        assert "aa_auto_sdr" in readme
        # Should warn users not to edit manually.
        assert "do not edit" in readme.lower() or "managed by" in readme.lower()
