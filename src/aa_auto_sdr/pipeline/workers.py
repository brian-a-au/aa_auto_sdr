"""Parallel batch worker pool — see spec §3.2.

ThreadPoolExecutor-backed parallel runner for --batch. A single shared
AaClient (thread-safe for read methods) and optional shared ValidationCache
are forwarded to every worker. worker_id is stamped onto a threading.local
so WorkerIdFilter (in core/logging.py) can inject it onto every log record
emitted from a worker thread.

SIGINT/KeyboardInterrupt during a run cancels pending futures and re-raises.
fail_fast=True cancels pending futures on the first AaAutoSdrError.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, CancelledError, Future, ThreadPoolExecutor, as_completed, wait
from datetime import datetime
from pathlib import Path

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import (
    AaAutoSdrError,
    ApiError,
    AuthError,
    ConfigError,
    OutputError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult
from aa_auto_sdr.sdr.builder import ComponentFilter

logger = logging.getLogger(__name__)

# Thread-local storage for worker_id. The WorkerIdFilter in core/logging.py
# reads from this to stamp every log record emitted from a worker thread.
_worker_local: threading.local = threading.local()


def get_current_worker_id() -> int | None:
    """Return the worker_id of the current thread, or None if not in a worker."""
    return getattr(_worker_local, "worker_id", None)


# ---------------------------------------------------------------------------
# Exit-code map — duplicated from batch.py to avoid future circular import
# (Task 4 will make batch.py import run_parallel from this module).
# Module-level constant: no lazy init or lock needed.
# ---------------------------------------------------------------------------

_EXIT_CODE_BY_TYPE: dict[type[AaAutoSdrError], int] = {
    ConfigError: ExitCode.CONFIG.value,
    AuthError: ExitCode.AUTH.value,
    ApiError: ExitCode.API.value,
    ReportSuiteNotFoundError: ExitCode.NOT_FOUND.value,
    OutputError: ExitCode.OUTPUT.value,
}


def _exit_code_for(exc: AaAutoSdrError) -> int:
    """Match generate.py's exit-code policy. Most-specific class wins; fallback = GENERIC."""
    for cls in type(exc).__mro__:
        if cls in _EXIT_CODE_BY_TYPE:
            return _EXIT_CODE_BY_TYPE[cls]
    return ExitCode.GENERIC.value


def _bytes_for(result: RunResult) -> int:
    """Sum bytes across all output files in a RunResult. Duplicate of batch._bytes_for
    to avoid a circular import (batch.py will import workers.py in Task 4)."""
    total = 0
    for path in result.outputs:
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------
# Per-RSID work function — module-level so tests can monkeypatch it
# ---------------------------------------------------------------------------


def _run_single_for_batch(
    *,
    rsid: str,
    client: AaClient,
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
    snapshot_dir: Path | None = None,
    component_filter: ComponentFilter | None = None,
    cache: object = None,
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
    fail_on_quality: str | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0
    # v1.15.0 — git integration
    git_commit: bool = False,
    git_push: bool = False,
    git_message: str | None = None,
    # v1.16.0 — template-fill writer config
    template_path: Path | None = None,
    template_organization: str | None = None,
    # v1.18.0 — Notion writer per-run config
    notion_force_new: bool = False,
    notion_registry_database: str | None = None,
    no_notion_registry: bool = False,
    # v1.20.0 — Notion registry company threading
    notion_company: str | None = None,
) -> RunResult:
    """Thin wrapper around pipeline.single.run_single for use in worker threads.

    Kept as a module-level function (not a closure) so tests can monkeypatch it
    without needing access to any enclosing scope.

    v1.12.0: `cache` is wired through to the quality-engine first caller.
    `fail_on_quality` / `quality_report` thread the gate + report flags from
    `run_parallel` down to single.run_single — without this, parallel batches
    silently bypassed the gate that the sequential path already honored.
    """
    # Lazy import: heavy deps are deferred until a worker actually runs.
    from aa_auto_sdr.pipeline import single
    from aa_auto_sdr.sdr.quality import SeverityLevel

    foq = SeverityLevel(fail_on_quality) if fail_on_quality else None

    return single.run_single(
        client=client,
        rsid=rsid,
        formats=formats,
        output_dir=output_dir,
        captured_at=captured_at,
        tool_version=tool_version,
        snapshot_dir=snapshot_dir,
        component_filter=component_filter,
        audit_naming=audit_naming,
        flag_stale=flag_stale,
        fail_on_quality=foq,
        quality_report=quality_report,
        cache=cache,  # type: ignore[arg-type]
        git_commit=git_commit,
        git_push=git_push,
        git_message=git_message,
        template_path=template_path,
        template_organization=template_organization,
        notion_force_new=notion_force_new,
        notion_registry_database=notion_registry_database,
        no_notion_registry=no_notion_registry,
        notion_company=notion_company,
    )


def _run_with_worker_id(
    *,
    worker_id: int,
    rsid: str,
    client: AaClient,
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
    snapshot_dir: Path | None,
    component_filter: ComponentFilter | None,
    cache: object,
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
    fail_on_quality: str | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0
    # v1.15.0 — git integration
    git_commit: bool = False,
    git_push: bool = False,
    git_message: str | None = None,
    # v1.16.0 — template-fill writer config
    template_path: Path | None = None,
    template_organization: str | None = None,
    # v1.18.0 — Notion writer per-run config
    notion_force_new: bool = False,
    notion_registry_database: str | None = None,
    no_notion_registry: bool = False,
    # v1.20.0 — Notion registry company threading
    notion_company: str | None = None,
) -> RunResult:
    """Stamp worker_id onto threading.local, run the single-RSID pipeline, clear on exit.

    Also stamps the wall-clock duration onto the returned RunResult so that
    per-RSID duration_seconds is correct on the parallel path (Fix A / bug_001).
    """
    _worker_local.worker_id = worker_id
    started = time.monotonic()
    try:
        result = _run_single_for_batch(
            rsid=rsid,
            client=client,
            formats=formats,
            output_dir=output_dir,
            captured_at=captured_at,
            tool_version=tool_version,
            snapshot_dir=snapshot_dir,
            component_filter=component_filter,
            cache=cache,
            audit_naming=audit_naming,
            flag_stale=flag_stale,
            fail_on_quality=fail_on_quality,
            quality_report=quality_report,
            git_commit=git_commit,
            git_push=git_push,
            git_message=git_message,
            template_path=template_path,
            template_organization=template_organization,
            notion_force_new=notion_force_new,
            notion_registry_database=notion_registry_database,
            no_notion_registry=no_notion_registry,
            notion_company=notion_company,
        )
        return dataclasses.replace(result, duration_seconds=time.monotonic() - started)
    finally:
        # Clear the worker_id so it doesn't bleed into any subsequent use of
        # the same thread (ThreadPoolExecutor reuses threads).
        with contextlib.suppress(AttributeError):
            del _worker_local.worker_id


def run_parallel(
    *,
    client: AaClient,
    rsids: list[str],
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
    workers: int = 4,
    fail_fast: bool = False,
    snapshot_dir: Path | None = None,
    component_filter: ComponentFilter | None = None,
    cache: object = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    failure_callback: Callable[[int, int, str, str], None] | None = None,
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
    fail_on_quality: str | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0
    # v1.15.0 — git integration
    git_commit: bool = False,
    git_push: bool = False,
    git_message: str | None = None,
    # v1.16.0 — template-fill writer config
    template_path: Path | None = None,
    template_organization: str | None = None,
    # v1.18.0 — Notion writer per-run config
    notion_force_new: bool = False,
    notion_registry_database: str | None = None,
    no_notion_registry: bool = False,
    # v1.20.0 — Notion registry company threading
    notion_company: str | None = None,
) -> BatchResult:
    """Run per-RSID SDR generation in parallel via a ThreadPoolExecutor.

    Args:
        client: Single shared AaClient forwarded to all workers.
        rsids: Canonical RSIDs (caller responsible for resolution + dedup).
        workers: Thread-pool size.
        fail_fast: If True, cancel pending futures on the first AaAutoSdrError.
        cache: Optional ValidationCache shared across all workers.
        progress_callback: Optional `(i, total, rsid)` called before each submit.
        failure_callback: Optional `(i, total, rsid, message)` called on failure.

    Returns BatchResult with per-RSID successes and failures.

    Raises KeyboardInterrupt if interrupted (pending futures are cancelled first).
    """
    batch_id = uuid.uuid4().hex[:8]
    successes: list[RunResult] = []
    failures: list[BatchFailure] = []
    total_bytes = 0
    total = len(rsids)
    started = time.monotonic()

    logger.info(
        "parallel_batch_start batch_id=%s count=%s workers=%s",
        batch_id,
        total,
        workers,
        extra={"batch_id": batch_id, "count": total, "workers": workers},
    )

    # Map future → {"submission_index": int, "rsid": str} so we can reconstruct
    # context when the future completes (as_completed gives no ordering guarantee).
    future_to_ctx: dict[Future[RunResult], dict[str, object]] = {}

    def _make_future(executor: ThreadPoolExecutor, idx: int, rsid: str) -> Future[RunResult]:
        """Submit one RSID to the executor and register it in future_to_ctx."""
        if progress_callback is not None:
            progress_callback(idx + 1, total, rsid)
        future = executor.submit(
            _run_with_worker_id,
            worker_id=idx,
            rsid=rsid,
            client=client,
            formats=formats,
            output_dir=output_dir,
            captured_at=captured_at,
            tool_version=tool_version,
            snapshot_dir=snapshot_dir,
            component_filter=component_filter,
            cache=cache,
            audit_naming=audit_naming,
            flag_stale=flag_stale,
            fail_on_quality=fail_on_quality,
            quality_report=quality_report,
            git_commit=git_commit,
            git_push=git_push,
            git_message=git_message,
            template_path=template_path,
            template_organization=template_organization,
            notion_force_new=notion_force_new,
            notion_registry_database=notion_registry_database,
            no_notion_registry=no_notion_registry,
            notion_company=notion_company,
        )
        future_to_ctx[future] = {"submission_index": idx, "rsid": rsid}
        return future

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="aa-worker") as executor:
        if fail_fast:
            # Lazy submission: only submit `workers` tasks at a time.
            # When a failure occurs, we cancel any pending (not-yet-started)
            # futures and stop submitting new ones. This is the only approach
            # that reliably prevents later RSIDs from being picked up by an
            # idle thread before cancel() takes effect.
            pending: list[Future[RunResult]] = []
            rsid_iter = iter(enumerate(rsids))

            # Seed the pool with the first `workers` tasks.
            for idx, rsid in rsid_iter:
                pending.append(_make_future(executor, idx, rsid))
                if len(pending) >= workers:
                    break

            # Process results as they complete; submit the next task on success.
            # wait(FIRST_COMPLETED) avoids the O(N²) waiter-installation cost of
            # calling next(as_completed(pending)) on a new snapshot each iteration.
            try:
                failed = False
                pending_set: set[Future[RunResult]] = set(pending)
                while pending_set and not failed:
                    done_set, pending_set = wait(pending_set, return_when=FIRST_COMPLETED)
                    for done_future in done_set:
                        ctx = future_to_ctx[done_future]
                        submission_index = ctx["submission_index"]
                        rsid = ctx["rsid"]
                        try:
                            result = done_future.result()
                        except CancelledError:
                            failures.append(
                                BatchFailure(
                                    rsid=rsid,
                                    error_type="CancelledError",
                                    message="cancelled",
                                    exit_code=ExitCode.GENERIC.value,
                                )
                            )
                        except AaAutoSdrError as exc:
                            message = str(exc)
                            exit_code = _exit_code_for(exc)
                            logger.error(
                                "rsid_failure rsid=%s batch_id=%s error_class=%s",
                                rsid,
                                batch_id,
                                type(exc).__name__,
                                extra={
                                    "rsid": rsid,
                                    "batch_id": batch_id,
                                    "exit_code": exit_code,
                                    "error_class": type(exc).__name__,
                                    "worker_id": submission_index,
                                },
                            )
                            if failure_callback is not None:
                                failure_callback(submission_index + 1, total, rsid, message)
                            failures.append(
                                BatchFailure(
                                    rsid=rsid,
                                    error_type=type(exc).__name__,
                                    message=message,
                                    exit_code=exit_code,
                                )
                            )
                            # Mark failed but continue draining the rest of done_set
                            # so co-completed futures are not silently dropped.
                            failed = True
                        else:
                            total_bytes += _bytes_for(result)
                            successes.append(result)
                            logger.info(
                                "rsid_complete rsid=%s batch_id=%s duration_ms=%s",
                                rsid,
                                batch_id,
                                int(result.duration_seconds * 1000),
                                extra={
                                    "rsid": rsid,
                                    "batch_id": batch_id,
                                    "duration_ms": int(result.duration_seconds * 1000),
                                    "count": len(result.outputs),
                                    "worker_id": submission_index,
                                },
                            )
                            # Submit the next task from the iterator only if no
                            # failure has been detected yet in this done_set batch.
                            if not failed:
                                try:
                                    idx, rsid = next(rsid_iter)
                                    new_future = _make_future(executor, idx, rsid)
                                    pending_set.add(new_future)
                                except StopIteration:
                                    pass
                    if failed:
                        # Cancel all remaining pending futures now that the
                        # entire done_set has been drained. Not-yet-started
                        # futures cancel cleanly and are recorded as
                        # CancelledError so progress accounting matches
                        # BatchResult (Fix B / bug_020). A future that is
                        # already RUNNING cannot be cancelled — it completes
                        # and writes its outputs regardless (the executor's
                        # shutdown waits for it), so record its true outcome
                        # instead of a fictitious "cancelled".
                        for pf in pending_set:
                            pf_ctx = future_to_ctx.get(pf)
                            if pf.cancel():
                                if pf_ctx is not None:
                                    failures.append(
                                        BatchFailure(
                                            rsid=pf_ctx["rsid"],
                                            error_type="CancelledError",
                                            message="cancelled",
                                            exit_code=ExitCode.GENERIC.value,
                                        )
                                    )
                                continue
                            try:
                                late_result = pf.result()
                            except AaAutoSdrError as exc:
                                failures.append(
                                    BatchFailure(
                                        rsid=pf_ctx["rsid"] if pf_ctx else "?",
                                        error_type=type(exc).__name__,
                                        message=str(exc),
                                        exit_code=_exit_code_for(exc),
                                    )
                                )
                            else:
                                total_bytes += _bytes_for(late_result)
                                successes.append(late_result)
                        pending_set = set()
            except KeyboardInterrupt:
                for pf in pending_set:
                    pf.cancel()
                raise

        else:
            # Normal mode: submit all RSIDs upfront and collect results as they
            # complete. Continue-on-error.
            for idx, rsid in enumerate(rsids):
                _make_future(executor, idx, rsid)

            # --- Collection phase ---
            try:
                for future in as_completed(future_to_ctx):
                    ctx = future_to_ctx[future]
                    submission_index = ctx["submission_index"]
                    rsid = ctx["rsid"]
                    try:
                        result = future.result()
                    except CancelledError:
                        # Cancelled (e.g. KeyboardInterrupt) — record as failure.
                        logger.debug(
                            "parallel_worker_cancelled rsid=%s batch_id=%s",
                            rsid,
                            batch_id,
                            extra={"rsid": rsid, "batch_id": batch_id},
                        )
                        failures.append(
                            BatchFailure(
                                rsid=rsid,
                                error_type="CancelledError",
                                message="cancelled",
                                exit_code=ExitCode.GENERIC.value,
                            )
                        )
                    except AaAutoSdrError as exc:
                        message = str(exc)
                        exit_code = _exit_code_for(exc)
                        logger.error(
                            "rsid_failure rsid=%s batch_id=%s error_class=%s",
                            rsid,
                            batch_id,
                            type(exc).__name__,
                            extra={
                                "rsid": rsid,
                                "batch_id": batch_id,
                                "exit_code": exit_code,
                                "error_class": type(exc).__name__,
                                "worker_id": submission_index,
                            },
                        )
                        if failure_callback is not None:
                            failure_callback(submission_index + 1, total, rsid, message)
                        failures.append(
                            BatchFailure(
                                rsid=rsid,
                                error_type=type(exc).__name__,
                                message=message,
                                exit_code=exit_code,
                            )
                        )
                    else:
                        total_bytes += _bytes_for(result)
                        successes.append(result)
                        logger.info(
                            "rsid_complete rsid=%s batch_id=%s duration_ms=%s",
                            rsid,
                            batch_id,
                            int(result.duration_seconds * 1000),
                            extra={
                                "rsid": rsid,
                                "batch_id": batch_id,
                                "duration_ms": int(result.duration_seconds * 1000),
                                "count": len(result.outputs),
                                "worker_id": submission_index,
                            },
                        )
            except KeyboardInterrupt:
                # Cancel all remaining pending futures and re-raise.
                for pending_future in future_to_ctx:
                    pending_future.cancel()
                raise

    duration_seconds = time.monotonic() - started
    logger.info(
        "batch_summary batch_id=%s ok=%s failed=%s duration_ms=%s",
        batch_id,
        len(successes),
        len(failures),
        int(duration_seconds * 1000),
        extra={
            "batch_id": batch_id,
            "count": len(successes),
            "count_failed": len(failures),
            "duration_ms": int(duration_seconds * 1000),
        },
    )
    return BatchResult(
        successes=successes,
        failures=failures,
        total_duration_seconds=duration_seconds,
        total_output_bytes=total_bytes,
        batch_id=batch_id,
    )
