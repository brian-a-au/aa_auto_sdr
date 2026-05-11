"""`git show <ref>:<path>` wrapper for snapshot resolution.

Subprocess only — we don't want a libgit2 dependency for a single shell-out."""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
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


# --- v1.15.0: write operations ----------------------------------------------


@dataclass(frozen=True, slots=True)
class GitOpResult:
    """Outcome of a git operation. Used by the pipeline orchestrators."""

    ok: bool
    committed: bool = False
    pushed: bool = False
    commit_sha: str | None = None
    error_kind: str | None = None  # "GitInitError" | "GitCommitError" | "GitPushError" | None
    error_message: str | None = None


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout_s: int = 30,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `cwd` and return the CompletedProcess.

    Centralizes subprocess invocation so timeouts and capture defaults are
    consistent across write operations. Caller decides whether returncode != 0
    means failure or just "nothing to do" (e.g. `git diff --cached --quiet`).
    """
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout_s,
    )


_SNAPSHOT_README = """\
# aa_auto_sdr snapshot store

This directory is a git-versioned audit trail of Adobe Analytics SDR
snapshots, managed by `aa_auto_sdr --git-commit`.

**Do not edit files in this directory manually.** Snapshot files are
written by the tool and committed automatically. Each commit corresponds
to a single SDR build run for one report suite.

To push history to a remote, run `git remote add origin <url>` inside
this directory and re-invoke `aa_auto_sdr --git-commit --git-push`.
"""


def is_git_repository(path: Path) -> bool:
    """True iff `path` is the root of a git working tree."""
    if not path.is_dir():
        return False
    try:
        result = _run_git(
            ["rev-parse", "--is-inside-work-tree"],
            cwd=path,
            timeout_s=5,
        )
    except FileNotFoundError, subprocess.TimeoutExpired:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_init_snapshot_repo(snapshot_dir: Path) -> GitOpResult:
    """Initialize `snapshot_dir` as a git repo and create the initial commit.

    Idempotent: if `snapshot_dir` is already a git repo, returns ok=True
    without re-initializing.

    Side effects on a fresh repo:
    - `git init --initial-branch=main`
    - `git config --local commit.gpgsign false` (avoid unattended GPG prompts)
    - Writes `README.md` identifying the directory as an aa_auto_sdr snapshot store.
    - Creates the initial commit with that README.
    """
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if is_git_repository(snapshot_dir):
        return GitOpResult(ok=True)

    init = _run_git(["init", "--initial-branch=main"], cwd=snapshot_dir)
    if init.returncode != 0:
        return GitOpResult(
            ok=False,
            error_kind="GitInitError",
            error_message=init.stderr.strip() or init.stdout.strip(),
        )

    cfg = _run_git(["config", "--local", "commit.gpgsign", "false"], cwd=snapshot_dir)
    if cfg.returncode != 0:
        return GitOpResult(
            ok=False,
            error_kind="GitInitError",
            error_message=f"git config commit.gpgsign failed: {cfg.stderr.strip()}",
        )

    readme_path = snapshot_dir / "README.md"
    readme_path.write_text(_SNAPSHOT_README)

    add = _run_git(["add", "README.md"], cwd=snapshot_dir)
    if add.returncode != 0:
        return GitOpResult(
            ok=False,
            error_kind="GitInitError",
            error_message=add.stderr.strip(),
        )

    commit = _run_git(
        ["commit", "-m", "Initial commit: aa_auto_sdr snapshot store"],
        cwd=snapshot_dir,
    )
    if commit.returncode != 0:
        return GitOpResult(
            ok=False,
            error_kind="GitInitError",
            error_message=commit.stderr.strip() or commit.stdout.strip(),
        )

    sha = _run_git(["rev-parse", "HEAD"], cwd=snapshot_dir)
    commit_sha = sha.stdout.strip() if sha.returncode == 0 else None
    logger.info(
        "git_init_repo path=%s initial_commit=%s",
        snapshot_dir,
        commit_sha,
        extra={"path": str(snapshot_dir), "initial_commit": commit_sha},
    )
    return GitOpResult(
        ok=True,
        committed=True,
        commit_sha=commit_sha,
    )


_COMPONENT_TYPES_ORDER = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
)


def generate_commit_message(
    *,
    rsid: str,
    captured_at: str,
    change_summary: dict[str, object] | None,
    watch_cycle: int | None = None,
) -> str:
    """Build the default commit message for a snapshot commit.

    Subject: ``SDR snapshot: <rsid> @ <captured_at>`` truncated to <=72 chars.
    Body: per-component-type counts when `change_summary` is provided, else
    ``Initial snapshot``.
    Footer: ``(watch cycle <n>)`` when `watch_cycle` is provided.
    """
    subject = f"SDR snapshot: {rsid} @ {captured_at}"
    if len(subject) > 72:
        subject = subject[:71] + "…"

    if change_summary is None:
        body = "Initial snapshot"
    else:
        by_type = change_summary.get("by_type", {}) or {}
        lines: list[str] = []
        for ct in _COMPONENT_TYPES_ORDER:
            counts = by_type.get(ct)
            if not counts:
                continue
            a = counts.get("added", 0)
            r = counts.get("removed", 0)
            m = counts.get("modified", 0)
            lines.append(f"{ct + ':':<12}+{a} -{r} ~{m}")
        body = "\n".join(lines) if lines else "Snapshot updated (no per-type counts available)"

    parts = [subject, "", body]
    if watch_cycle is not None:
        parts.extend(["", f"(watch cycle {watch_cycle})"])
    return "\n".join(parts) + "\n"


def git_commit_snapshot(
    snapshot_dir: Path,
    *,
    rsid: str,
    message: str | None,
    push: bool,
    timeout_s: int = 30,
) -> GitOpResult:
    """Stage `<snapshot_dir>/<rsid>/*`, commit, optionally push.

    Auto-inits the snapshot dir as a git repo on first invocation. Skips
    the commit (returns ``ok=True, committed=False``) when there's no
    staged diff. Returns ``error_kind="GitCommitError"`` or
    ``error_kind="GitPushError"`` on failure.

    If `message` is None, generates a default via `generate_commit_message`
    using the RSID and current UTC timestamp. The full per-cycle message
    (with change counts + watch_cycle footer) is built by the caller and
    passed in; this fallback exists for one-shot invocations where the
    caller may not have a change summary handy.
    """
    started = time.monotonic()
    # Lazy init.
    if not is_git_repository(snapshot_dir):
        init = git_init_snapshot_repo(snapshot_dir)
        if not init.ok:
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "git_op_failed rsid=%s op=%s error_class=%s duration_ms=%d",
                rsid,
                "init",
                init.error_kind,
                duration_ms,
                extra={
                    "rsid": rsid,
                    "op": "init",
                    "error_class": init.error_kind,
                    "duration_ms": duration_ms,
                },
            )
            return init

    # Nothing to commit if the per-RSID subdir doesn't exist yet — bail
    # before `git add` so we don't surface 'pathspec did not match any files'
    # (modern git's exit-code 128) as a spurious failure.
    rsid_dir = snapshot_dir / rsid
    if not rsid_dir.exists():
        return GitOpResult(ok=True, committed=False)

    # Stage everything under <rsid>/ (matches cja's pathspec scoping).
    pathspec = f"{rsid}/"
    add = _run_git(["add", "-A", "--", pathspec], cwd=snapshot_dir, timeout_s=timeout_s)
    if add.returncode != 0:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "git_op_failed rsid=%s op=%s error_class=%s duration_ms=%d",
            rsid,
            "commit",
            "GitCommitError",
            duration_ms,
            extra={
                "rsid": rsid,
                "op": "commit",
                "error_class": "GitCommitError",
                "duration_ms": duration_ms,
            },
        )
        return GitOpResult(
            ok=False,
            error_kind="GitCommitError",
            error_message=f"git add {pathspec} failed: {add.stderr.strip()}",
        )

    # Anything to commit?
    diff = _run_git(["diff", "--cached", "--quiet"], cwd=snapshot_dir, timeout_s=10)
    if diff.returncode == 0:
        # No staged changes; not an error.
        return GitOpResult(ok=True, committed=False)

    # Build the message if the caller didn't supply one.
    if message is None:
        from datetime import UTC, datetime

        message = generate_commit_message(
            rsid=rsid,
            captured_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            change_summary=None,
        )

    commit = _run_git(
        ["commit", "-m", message],
        cwd=snapshot_dir,
        timeout_s=timeout_s,
    )
    if commit.returncode != 0:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "git_op_failed rsid=%s op=%s error_class=%s duration_ms=%d",
            rsid,
            "commit",
            "GitCommitError",
            duration_ms,
            extra={
                "rsid": rsid,
                "op": "commit",
                "error_class": "GitCommitError",
                "duration_ms": duration_ms,
            },
        )
        return GitOpResult(
            ok=False,
            error_kind="GitCommitError",
            error_message=commit.stderr.strip() or commit.stdout.strip(),
        )

    rev = _run_git(["rev-parse", "HEAD"], cwd=snapshot_dir, timeout_s=5)
    commit_sha = rev.stdout.strip() if rev.returncode == 0 else None

    if not push:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "git_commit_complete rsid=%s commit_sha=%s pushed=%s duration_ms=%d",
            rsid,
            commit_sha,
            False,
            duration_ms,
            extra={
                "rsid": rsid,
                "commit_sha": commit_sha,
                "pushed": False,
                "duration_ms": duration_ms,
            },
        )
        return GitOpResult(
            ok=True,
            committed=True,
            pushed=False,
            commit_sha=commit_sha,
        )

    push_result = _run_git(["push"], cwd=snapshot_dir, timeout_s=60)
    if push_result.returncode != 0:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "git_op_failed rsid=%s op=%s error_class=%s duration_ms=%d",
            rsid,
            "push",
            "GitPushError",
            duration_ms,
            extra={
                "rsid": rsid,
                "op": "push",
                "error_class": "GitPushError",
                "duration_ms": duration_ms,
            },
        )
        return GitOpResult(
            ok=False,
            committed=True,
            pushed=False,
            commit_sha=commit_sha,
            error_kind="GitPushError",
            error_message=push_result.stderr.strip() or push_result.stdout.strip(),
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "git_commit_complete rsid=%s commit_sha=%s pushed=%s duration_ms=%d",
        rsid,
        commit_sha,
        True,
        duration_ms,
        extra={
            "rsid": rsid,
            "commit_sha": commit_sha,
            "pushed": True,
            "duration_ms": duration_ms,
        },
    )
    return GitOpResult(
        ok=True,
        committed=True,
        pushed=True,
        commit_sha=commit_sha,
    )
