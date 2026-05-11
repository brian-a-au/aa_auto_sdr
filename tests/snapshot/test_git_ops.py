"""snapshot.git write operations — real-git subprocess via tmp_path."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from aa_auto_sdr.snapshot.git import (
    git_commit_snapshot,
    git_init_snapshot_repo,
    is_git_repository,
)


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    """Ensure git commit identity is set without relying on the dev's global config.

    Covers both the ``Initial commit`` inside ``git_init_snapshot_repo`` and any
    subsequent commits in individual tests. This avoids silent failures on CI
    where no global user.email/user.name is configured.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


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

    def test_returns_false_for_subdir_of_existing_repo(self, tmp_path: Path) -> None:
        """P3 regression — is_git_repository must return False for a subdirectory
        of a git repo, even though `git rev-parse --is-inside-work-tree` would
        return true. Prevents lazy auto-init from committing snapshot files into
        a parent repository when --snapshot-dir is a subdir of an unrelated checkout.
        """
        git_init_snapshot_repo(tmp_path)
        subdir = tmp_path / "snapshots"
        subdir.mkdir()
        # Even though subdir is inside the repo, it is NOT the repo root.
        assert is_git_repository(subdir) is False

    def test_returns_true_for_repo_root_after_git_init_snapshot_repo(self, tmp_path: Path) -> None:
        """Companion: the repo root itself must still return True (no regression)."""
        git_init_snapshot_repo(tmp_path)
        assert is_git_repository(tmp_path) is True


class TestGitInitSnapshotRepo:
    def test_creates_git_dir_and_initial_commit(self, tmp_path: Path) -> None:
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
        git_init_snapshot_repo(tmp_path)
        # Second init: idempotent — returns ok without re-initializing.
        result = git_init_snapshot_repo(tmp_path)
        assert result.ok is True
        # README still intact; only one initial commit.
        log = _run_git(["log", "--oneline"], tmp_path)
        assert log.stdout.count("\n") == 1  # only the initial commit

    def test_sets_commit_gpgsign_false_locally(self, tmp_path: Path) -> None:
        git_init_snapshot_repo(tmp_path)
        config = _run_git(["config", "--local", "commit.gpgsign"], tmp_path)
        assert config.stdout.strip() == "false"

    def test_initial_branch_is_main(self, tmp_path: Path) -> None:
        git_init_snapshot_repo(tmp_path)
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], tmp_path)
        assert branch.stdout.strip() == "main"

    def test_readme_identifies_snapshot_store(self, tmp_path: Path) -> None:
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


class TestGitPush:
    @pytest.fixture
    def repo_with_remote(self, tmp_path: Path) -> tuple[Path, Path]:
        """Init a snapshot repo + a local bare-repo remote; wire them together."""
        snapshot_dir = tmp_path / "snapshots"
        remote_dir = tmp_path / "remote.git"
        # Create a bare remote.
        subprocess.run(
            ["git", "init", "--bare", str(remote_dir)],
            check=True,
            capture_output=True,
        )
        # Init the snapshot dir and point it at the bare remote.
        git_init_snapshot_repo(snapshot_dir)
        subprocess.run(
            ["git", "remote", "add", "origin", str(remote_dir)],
            cwd=snapshot_dir,
            check=True,
            capture_output=True,
        )
        # Configure a default upstream so plain `git push` works.
        subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=snapshot_dir,
            check=True,
            capture_output=True,
        )
        return snapshot_dir, remote_dir

    def test_push_after_commit(self, repo_with_remote: tuple[Path, Path]) -> None:
        snapshot_dir, remote_dir = repo_with_remote
        _write_snapshot(snapshot_dir, "rs_a", '{"rsid":"rs_a"}')
        result = git_commit_snapshot(
            snapshot_dir,
            rsid="rs_a",
            message="test",
            push=True,
        )
        assert result.ok is True
        assert result.committed is True
        assert result.pushed is True
        log = subprocess.run(
            ["git", "log", "--oneline", "main"],
            cwd=remote_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.commit_sha[:7] in log.stdout

    def test_push_fail_without_remote(self, tmp_path: Path) -> None:
        # Repo with no remote configured.
        git_init_snapshot_repo(tmp_path)
        _write_snapshot(tmp_path, "rs_a", '{"rsid":"rs_a"}')
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="test",
            push=True,
        )
        # Commit succeeds; push fails.
        assert result.committed is True
        assert result.ok is False
        assert result.pushed is False
        assert result.error_kind == "GitPushError"
        assert result.error_message  # non-empty stderr

    def test_no_diff_means_no_push(self, tmp_path: Path) -> None:
        # When there's no commit, push is also skipped.
        git_init_snapshot_repo(tmp_path)
        result = git_commit_snapshot(
            tmp_path,
            rsid="rs_a",
            message="x",
            push=True,
        )
        assert result.ok is True
        assert result.committed is False
        assert result.pushed is False


class TestGitCommitConcurrency:
    """Regression: parallel workers must not race on .git/index.lock (C2)."""

    def test_three_concurrent_commits_all_succeed(self, tmp_path: Path) -> None:
        """Spawn 3 threads each committing a different RSID to the same repo.

        Without _GIT_LOCK this test would fail frequently with
        ``index.lock`` errors. With the lock all 3 must succeed with
        distinct commit SHAs, and the log must have 4 commits total
        (initial + 3 per-RSID).
        """
        git_init_snapshot_repo(tmp_path)
        rsids = ["rs_alpha", "rs_beta", "rs_gamma"]
        results: list[tuple[str, object]] = []
        errors: list[BaseException] = []

        def commit_one(rsid: str) -> None:
            rsid_dir = tmp_path / rsid
            rsid_dir.mkdir(parents=True, exist_ok=True)
            (rsid_dir / "snap.json").write_text(f'{{"rsid":"{rsid}"}}')
            try:
                r = git_commit_snapshot(
                    tmp_path,
                    rsid=rsid,
                    message=f"snapshot for {rsid}",
                    push=False,
                )
                results.append((rsid, r))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=commit_one, args=(rsid,)) for rsid in rsids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert len(results) == 3
        for rsid, result in results:
            assert result.ok is True, f"{rsid} failed: {result.error_message}"
            assert result.committed is True, f"{rsid} was not committed"
            assert result.commit_sha is not None

        # 3 distinct commit SHAs.
        shas = {r.commit_sha for _, r in results}
        assert len(shas) == 3

        # Git log: initial commit + 3 per-RSID = 4 total.
        log = _run_git(["log", "--oneline"], tmp_path)
        assert log.returncode == 0
        assert log.stdout.count("\n") == 4
