"""snapshot.git — coverage for git-binary-missing, init/commit failure paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.snapshot import git


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


def _completed(args: list[str], returncode: int, stderr: str = "") -> subprocess.CompletedProcess[str]:
    stdout = "a" * 40 if args == ["rev-parse", "HEAD"] and returncode == 0 else ""
    return subprocess.CompletedProcess(["git", *args], returncode, stdout=stdout, stderr=stderr)


def _selective_run_git(fail_ops: dict[str, int]):
    """Return a fake `_run_git` whose returncode depends on the git subcommand.

    `fail_ops` maps a subcommand (e.g. "init", "config") to a non-zero
    returncode; everything else returns 0.
    """

    def _run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        op = args[0]
        rc = fail_ops.get(op, 0)
        stderr = (
            "fatal: not a git repository"
            if args == ["rev-parse", "--show-toplevel"] and rc
            else f"{op} boom"
            if rc
            else ""
        )
        return _completed(args, rc, stderr=stderr)

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


def test_git_init_already_checked_skips_strict_repository_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_already_checked=True` (as passed by `git_commit_snapshot`, which has
    just run the same probe itself) must skip the internal
    `_probe_git_repository` call entirely — the init still proceeds normally."""
    calls = {"n": 0}

    def _spy(_path: Path) -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(git, "_probe_git_repository", _spy)
    monkeypatch.setattr(git, "_run_git", _selective_run_git({}))

    result = git.git_init_snapshot_repo(tmp_path, _already_checked=True)

    assert calls["n"] == 0
    assert result.ok is True


def test_git_init_default_still_probes_strict_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Public no-arg behavior is unchanged: the default still probes and
    short-circuits when the directory is already a repo."""
    calls = {"n": 0}

    def _spy(_path: Path) -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(git, "_probe_git_repository", _spy)

    result = git.git_init_snapshot_repo(tmp_path)

    assert calls["n"] == 1
    assert result.ok is True


# ---------------------------------------------------------------------------
# git_commit_snapshot — failure paths
# ---------------------------------------------------------------------------


def test_git_commit_returns_init_error_when_lazy_init_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git, "_probe_git_repository", lambda _p: False)
    failed = git.GitOpResult(ok=False, error_kind="GitInitError", error_message="init failed")
    monkeypatch.setattr(git, "git_init_snapshot_repo", lambda _d, **_kw: failed)

    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert result.error_message == failed.error_message
    assert result.ok is False
    assert result.error_kind == "GitInitError"


def test_git_commit_add_failure_returns_commit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "rs_a").mkdir()
    monkeypatch.setattr(git, "_probe_git_repository", lambda _p: True)
    monkeypatch.setattr(git, "_run_git", _selective_run_git({"add": 1}))

    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert result.ok is False
    assert result.error_kind == "GitCommitError"
    assert "add" in result.error_message


def test_git_commit_commit_failure_returns_commit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "rs_a").mkdir()
    monkeypatch.setattr(git, "_probe_git_repository", lambda _p: True)

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


@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired(["git", "rev-parse"], 5), OSError("probe failed")])
def test_uncertain_probe_does_not_mutate_existing_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    (tmp_path / "README.md").write_text("keep")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("preserve")
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args[:2] == ["rev-parse", "--show-toplevel"]:
            raise failure
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert not result.ok
    assert result.error_kind == "GitInitError"
    assert (tmp_path / "README.md").read_text() == "keep"
    assert (tmp_path / ".git" / "config").read_text() == "preserve"


def test_unexplained_probe_failure_with_git_metadata_does_not_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("keep")
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args == ["rev-parse", "--show-toplevel"]:
            return _completed(args, 128, "fatal: not a git repository")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert not result.ok
    assert result.error_kind == "GitInitError"
    assert (tmp_path / "README.md").read_text() == "keep"


def test_stat_denied_does_not_initialize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "README.md").write_text("keep")
    original = Path.stat

    def denied(path: Path, *args, **kwargs):
        if path == tmp_path:
            raise PermissionError("stat denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", denied)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert not result.ok
    assert result.error_kind == "GitInitError"
    assert (tmp_path / "README.md").read_text() == "keep"


@pytest.mark.parametrize("op", ["add", "diff", "commit", "rev-parse", "push"])
@pytest.mark.parametrize("failure_type", ["timeout", "oserror"])
def test_subprocess_failure_is_structured_by_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str, failure_type: str
) -> None:
    assert git.git_init_snapshot_repo(tmp_path).ok
    suite = tmp_path / "rs_a"
    suite.mkdir()
    (suite / "snapshot.json").write_text("a")
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args[0] == op and (op != "rev-parse" or args[1:] == ["HEAD"]):
            if failure_type == "timeout":
                raise subprocess.TimeoutExpired(["git", *args], 1)
            raise OSError(f"{op} unavailable")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=True)
    assert not result.ok
    assert result.error_kind == ("GitPushError" if op == "push" else "GitCommitError")
    assert result.committed == (op in {"rev-parse", "push"})
    assert result.commit_sha is not None if op == "push" else result.commit_sha is None
    if op == "commit":
        assert not result.pushed


@pytest.mark.parametrize("op", ["init", "config", "add", "commit", "rev-parse"])
@pytest.mark.parametrize("failure_type", ["timeout", "oserror"])
def test_init_subprocess_failure_is_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, op: str, failure_type: str
) -> None:
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args[0] == op and (op != "rev-parse" or args == ["rev-parse", "HEAD"]):
            if failure_type == "timeout":
                raise subprocess.TimeoutExpired(["git", *args], 1)
            raise OSError(f"{op} unavailable")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_init_snapshot_repo(tmp_path)
    assert not result.ok
    assert result.error_kind == "GitInitError"
    assert result.committed == (op == "rev-parse")


def test_init_sha_failure_is_not_reported_as_suite_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args == ["rev-parse", "HEAD"]:
            return _completed(args, 128, "lookup failed")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=True)
    assert not result.ok
    assert not result.committed
    assert result.commit_sha is None
    assert result.error_kind == "GitInitError"


def test_suite_sha_nonzero_preserves_completed_commit_and_skips_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert git.git_init_snapshot_repo(tmp_path).ok
    suite = tmp_path / "rs_a"
    suite.mkdir()
    (suite / "snapshot.json").write_text("a")
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args == ["rev-parse", "HEAD"]:
            return _completed(args, 128, "lookup failed")
        if args == ["push"]:
            pytest.fail("push ran without a known commit SHA")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=True)
    assert not result.ok
    assert result.committed
    assert result.commit_sha is None
    assert not result.pushed
    assert result.error_kind == "GitCommitError"
    assert (original(["show", "HEAD:rs_a/snapshot.json"], cwd=tmp_path)).stdout == "a"


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt(), SystemExit()])
def test_control_flow_exceptions_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: BaseException
) -> None:
    def injected(args: list[str], **kwargs):
        raise interrupt

    monkeypatch.setattr(git, "_run_git", injected)
    with pytest.raises(type(interrupt)):
        git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)


def test_diff_exit_two_is_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git.git_init_snapshot_repo(tmp_path)
    suite = tmp_path / "rs_a"
    suite.mkdir()
    (suite / "snapshot.json").write_text("a")
    original = git._run_git

    def injected(args: list[str], **kwargs):
        if args[0] == "diff":
            return _completed(args, 2, "broken diff")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_a", message="m", push=False)
    assert not result.ok
    assert not result.committed
    assert result.error_kind == "GitCommitError"


@pytest.mark.parametrize("failure_type", ["timeout", "os_error", "nonzero"])
def test_missing_suite_discovery_failure_stops_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_type: str
) -> None:
    assert git.git_init_snapshot_repo(tmp_path).ok
    original = git._run_git
    calls: list[str] = []

    def injected(args: list[str], **kwargs):
        calls.append(args[0])
        if args[0] == "ls-files":
            if failure_type == "timeout":
                raise subprocess.TimeoutExpired(["git", *args], 1)
            if failure_type == "os_error":
                raise OSError("suite discovery unavailable")
            return _completed(args, 128, "suite discovery failed")
        return original(args, **kwargs)

    monkeypatch.setattr(git, "_run_git", injected)
    result = git.git_commit_snapshot(tmp_path, rsid="rs_absent", message="m", push=True)
    assert not result.ok
    assert result.error_kind == "GitCommitError"
    assert not result.committed
    assert result.commit_sha is None
    assert not result.pushed
    assert calls == ["rev-parse", "ls-files"]
