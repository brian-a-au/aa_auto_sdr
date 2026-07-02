"""snapshot.git — coverage for git-binary-missing, init/commit failure paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.snapshot import git


def _completed(args: list[str], returncode: int, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git", *args], returncode, stdout="", stderr=stderr)


def _selective_run_git(fail_ops: dict[str, int]):
    """Return a fake `_run_git` whose returncode depends on the git subcommand.

    `fail_ops` maps a subcommand (e.g. "init", "config") to a non-zero
    returncode; everything else returns 0.
    """

    def _run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        op = args[0]
        rc = fail_ops.get(op, 0)
        return _completed(args, rc, stderr=f"{op} boom" if rc else "")

    return _run


# ---------------------------------------------------------------------------
# git_show — git binary missing
# ---------------------------------------------------------------------------


def test_git_show_raises_when_git_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_git(*_a: object, **_kw: object) -> None:
        raise FileNotFoundError("no git here")

    monkeypatch.setattr(git.subprocess, "run", _no_git)
    with pytest.raises(SnapshotResolveError, match="git binary not found"):
        git.git_show(ref="HEAD", path="x.json", repo_root=tmp_path)


# ---------------------------------------------------------------------------
# is_git_repository — subprocess raises
# ---------------------------------------------------------------------------


def test_is_git_repository_returns_false_when_git_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_a: object, **_kw: object) -> None:
        raise FileNotFoundError("no git")

    monkeypatch.setattr(git, "_run_git", _raise)
    assert git.is_git_repository(tmp_path) is False


def test_is_git_repository_returns_false_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(*_a: object, **_kw: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)

    monkeypatch.setattr(git, "_run_git", _timeout)
    assert git.is_git_repository(tmp_path) is False


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — each subprocess-failure return
# ---------------------------------------------------------------------------


def test_git_init_returns_error_when_init_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git, "_run_git", _selective_run_git({"rev-parse": 1, "init": 1}))
    result = git.git_init_snapshot_repo(tmp_path)
    assert result.ok is False
    assert result.error_kind == "GitInitError"
    assert "init boom" in result.error_message


def test_git_init_returns_error_when_gpgsign_config_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git, "_run_git", _selective_run_git({"rev-parse": 1, "config": 1}))
    result = git.git_init_snapshot_repo(tmp_path)
    assert result.ok is False
    assert result.error_kind == "GitInitError"
    assert "gpgsign" in result.error_message


def test_git_init_returns_error_when_add_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git, "_run_git", _selective_run_git({"rev-parse": 1, "add": 1}))
    result = git.git_init_snapshot_repo(tmp_path)
    assert result.ok is False
    assert result.error_kind == "GitInitError"
    assert "add boom" in result.error_message


def test_git_init_returns_error_when_initial_commit_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git, "_run_git", _selective_run_git({"rev-parse": 1, "commit": 1}))
    result = git.git_init_snapshot_repo(tmp_path)
    assert result.ok is False
    assert result.error_kind == "GitInitError"
    assert "commit boom" in result.error_message


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — _already_checked skip-redundant-probe micro
# ---------------------------------------------------------------------------


def test_git_init_already_checked_skips_is_git_repository_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_already_checked=True` (as passed by `git_commit_snapshot`, which has
    just run the same probe itself) must skip the internal
    `is_git_repository` call entirely — the init still proceeds normally."""
    calls = {"n": 0}

    def _spy(_path: Path) -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(git, "is_git_repository", _spy)
    monkeypatch.setattr(git, "_run_git", _selective_run_git({}))

    result = git.git_init_snapshot_repo(tmp_path, _already_checked=True)

    assert calls["n"] == 0
    assert result.ok is True


def test_git_init_default_still_probes_is_git_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Public no-arg behavior is unchanged: the default still probes and
    short-circuits when the directory is already a repo."""
    calls = {"n": 0}

    def _spy(_path: Path) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(git, "is_git_repository", _spy)

    result = git.git_init_snapshot_repo(tmp_path)

    assert calls["n"] == 1
    assert result.ok is True


# ---------------------------------------------------------------------------
# git_commit_snapshot — failure paths
# ---------------------------------------------------------------------------


def test_git_commit_returns_init_error_when_lazy_init_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git, "is_git_repository", lambda _p: False)
    failed = git.GitOpResult(ok=False, error_kind="GitInitError", error_message="init failed")
    monkeypatch.setattr(git, "git_init_snapshot_repo", lambda _d, **_kw: failed)

    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert result is failed
    assert result.ok is False
    assert result.error_kind == "GitInitError"


def test_git_commit_add_failure_returns_commit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "rs_a").mkdir()
    monkeypatch.setattr(git, "is_git_repository", lambda _p: True)
    monkeypatch.setattr(git, "_run_git", _selective_run_git({"add": 1}))

    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert result.ok is False
    assert result.error_kind == "GitCommitError"
    assert "add" in result.error_message


def test_git_commit_commit_failure_returns_commit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "rs_a").mkdir()
    monkeypatch.setattr(git, "is_git_repository", lambda _p: True)

    def _run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        op = args[0]
        if op == "diff":
            # Non-zero from `git diff --cached --quiet` means there ARE staged
            # changes, so the commit is attempted.
            return _completed(args, 1)
        if op == "commit":
            return _completed(args, 1, stderr="commit boom")
        return _completed(args, 0)

    monkeypatch.setattr(git, "_run_git", _run)

    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert result.ok is False
    assert result.error_kind == "GitCommitError"
    assert "commit boom" in result.error_message
