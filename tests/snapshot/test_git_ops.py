"""snapshot.git write operations — real-git subprocess via tmp_path."""

from __future__ import annotations

import subprocess
from pathlib import Path

from aa_auto_sdr.snapshot.git import (
    git_commit_snapshot,
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


def _write_snapshot(snapshot_dir: Path, rsid: str, content: str) -> Path:
    """Test helper: write a fake snapshot file under <snapshot_dir>/<rsid>/."""
    rsid_dir = snapshot_dir / rsid
    rsid_dir.mkdir(parents=True, exist_ok=True)
    path = rsid_dir / "2026-05-11T15-00-00+00-00.json"
    path.write_text(content)
    return path


class TestGitCommitSnapshot:
    def test_commits_snapshot_file_after_init(self, tmp_path: Path) -> None:
        git_init_snapshot_repo(tmp_path)
        _write_snapshot(tmp_path, "rs_a", '{"rsid":"rs_a"}')
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="test commit",
            push=False,
        )
        assert result.ok is True
        assert result.committed is True
        assert result.commit_sha is not None
        assert len(result.commit_sha) == 40  # full git SHA
        assert result.error_kind is None

    def test_no_rsid_dir_returns_committed_false(self, tmp_path: Path) -> None:
        # rsid subdir doesn't exist → early-return path, no git operations
        # attempted.
        git_init_snapshot_repo(tmp_path)
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="should be skipped",
            push=False,
        )
        assert result.ok is True
        assert result.committed is False
        assert result.commit_sha is None

    def test_no_diff_after_existing_commit_returns_committed_false(self, tmp_path: Path) -> None:
        # Exercises the real `git diff --cached --quiet` no-op branch.
        git_init_snapshot_repo(tmp_path)
        _write_snapshot(tmp_path, "rs_a", '{"rsid":"rs_a"}')
        first = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="first commit",
            push=False,
        )
        assert first.committed is True
        second = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="should be skipped",
            push=False,
        )
        assert second.ok is True
        assert second.committed is False
        assert second.commit_sha is None
        log = _run_git(["log", "--oneline"], tmp_path)
        assert log.stdout.count("\n") == 2

    def test_auto_inits_on_first_call(self, tmp_path: Path) -> None:
        _write_snapshot(tmp_path, "rs_a", '{"rsid":"rs_a"}')
        assert is_git_repository(tmp_path) is False
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="first commit",
            push=False,
        )
        assert result.ok is True
        assert result.committed is True
        assert is_git_repository(tmp_path) is True

    def test_pathspec_scoping_only_stages_rsid_subdir(self, tmp_path: Path) -> None:
        git_init_snapshot_repo(tmp_path)
        _write_snapshot(tmp_path, "rs_a", '{"rsid":"rs_a"}')
        _write_snapshot(tmp_path, "rs_b", '{"rsid":"rs_b"}')
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="rs_a only",
            push=False,
        )
        assert result.ok is True
        show = _run_git(["show", "--name-only", "HEAD"], tmp_path)
        assert "rs_a/" in show.stdout
        assert "rs_b/" not in show.stdout

    def test_uses_auto_message_when_none_passed(self, tmp_path: Path) -> None:
        git_init_snapshot_repo(tmp_path)
        _write_snapshot(tmp_path, "rs_a", '{"rsid":"rs_a"}')
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message=None,
            push=False,
        )
        assert result.ok is True
        assert result.committed is True
        log = _run_git(["log", "-1", "--pretty=%s"], tmp_path)
        assert "SDR snapshot" in log.stdout or "Snapshot" in log.stdout
