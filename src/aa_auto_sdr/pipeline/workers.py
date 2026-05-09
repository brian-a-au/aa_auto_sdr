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
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
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
# ---------------------------------------------------------------------------

_EXIT_CODE_BY_TYPE: dict[type[AaAutoSdrError], int] | None = None
_EXIT_CODE_BY_TYPE_LOCK = threading.Lock()


def _populate_exit_code_map() -> dict[type[AaAutoSdrError], int]:
    global _EXIT_CODE_BY_TYPE  # noqa: PLW0603
    with _EXIT_CODE_BY_TYPE_LOCK:
        if _EXIT_CODE_BY_TYPE is None:
            _EXIT_CODE_BY_TYPE = {
                ConfigError: ExitCode.CONFIG.value,
                AuthError: ExitCode.AUTH.value,
                ApiError: ExitCode.API.value,
                ReportSuiteNotFoundError: ExitCode.NOT_FOUND.value,
                OutputError: ExitCode.OUTPUT.value,
            }
    return _EXIT_CODE_BY_TYPE


def _exit_code_for(exc: AaAutoSdrError) -> int:
    """Match generate.py's exit-code policy. Most-specific class wins; fallback = GENERIC."""
    code_map = _populate_exit_code_map()
    for cls in type(exc).__mro__:
        if cls in code_map:
            return code_map[cls]
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
    cache: object = None,  # noqa: ARG001 — reserved for v1.12.0 quality engine
) -> RunResult:
    """Thin wrapper around pipeline.single.run_single for use in worker threads.

    Kept as a module-level function (not a closure) so tests can monkeypatch it
    without needing access to any enclosing scope.

    The `cache` parameter is reserved for future use by the quality engine
    (v1.12.0). It is accepted here to ensure the call site in run_parallel can
    always pass it through without change.
    """
    # Lazy import: heavy deps are deferred until a worker actually runs.
    from aa_auto_sdr.pipeline import single

    return single.run_single(
        client=client,
        rsid=rsid,
        formats=formats,
        output_dir=output_dir,
        captured_at=captured_at,
        tool_version=tool_version,
        snapshot_dir=snapshot_dir,
        component_filter=component_filter,
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
) -> RunResult:
    """Stamp worker_id onto threading.local, run the single-RSID pipeline, clear on exit."""
    _worker_local.worker_id = worker_id
    try:
        return _run_single_for_batch(
            rsid=rsid,
            client=client,
            formats=formats,
            output_dir=output_dir,
            captured_at=captured_at,
            tool_version=tool_version,
            snapshot_dir=snapshot_dir,
            component_filter=component_filter,
            cache=cache,
        )
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
        "parallel_batch_start batch_id=%s rsids=%s workers=%s",
        batch_id,
        total,
        workers,
        extra={"batch_id": batch_id, "rsids": total, "workers": workers},
    )

    # Map future → (submission_index, rsid) so we can reconstruct context
    # when the future completes (as_completed gives no ordering guarantee).
    future_to_ctx: dict[Future[RunResult], tuple[int, str]] = {}

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
        )
        future_to_ctx[future] = (idx + 1, rsid)
        return future

    with ThreadPoolExecutor(max_workers=workers) as executor:
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
            try:
                failed = False
                while pending and not failed:
                    done_future = next(as_completed(pending))
                    pending.remove(done_future)
                    submission_index, rsid = future_to_ctx[done_future]
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
                            "parallel_rsid_failure rsid=%s batch_id=%s error_type=%s",
                            rsid,
                            batch_id,
                            type(exc).__name__,
                            extra={
                                "rsid": rsid,
                                "batch_id": batch_id,
                                "exit_code": exit_code,
                                "error_type": type(exc).__name__,
                            },
                        )
                        if failure_callback is not None:
                            failure_callback(submission_index, total, rsid, message)
                        failures.append(
                            BatchFailure(
                                rsid=rsid,
                                error_type=type(exc).__name__,
                                message=message,
                                exit_code=exit_code,
                            )
                        )
                        # Cancel remaining pending futures and stop.
                        for pf in pending:
                            pf.cancel()
                        failed = True
                    else:
                        total_bytes += _bytes_for(result)
                        successes.append(result)
                        logger.info(
                            "parallel_rsid_complete rsid=%s batch_id=%s duration_ms=%s",
                            rsid,
                            batch_id,
                            int(result.duration_seconds * 1000),
                            extra={
                                "rsid": rsid,
                                "batch_id": batch_id,
                                "duration_ms": int(result.duration_seconds * 1000),
                            },
                        )
                        # Submit the next task from the iterator.
                        try:
                            idx, rsid = next(rsid_iter)
                            pending.append(_make_future(executor, idx, rsid))
                        except StopIteration:
                            pass
            except KeyboardInterrupt:
                for pf in pending:
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
                    submission_index, rsid = future_to_ctx[future]
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
                            "parallel_rsid_failure rsid=%s batch_id=%s error_type=%s",
                            rsid,
                            batch_id,
                            type(exc).__name__,
                            extra={
                                "rsid": rsid,
                                "batch_id": batch_id,
                                "exit_code": exit_code,
                                "error_type": type(exc).__name__,
                            },
                        )
                        if failure_callback is not None:
                            failure_callback(submission_index, total, rsid, message)
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
                            "parallel_rsid_complete rsid=%s batch_id=%s duration_ms=%s",
                            rsid,
                            batch_id,
                            int(result.duration_seconds * 1000),
                            extra={
                                "rsid": rsid,
                                "batch_id": batch_id,
                                "duration_ms": int(result.duration_seconds * 1000),
                            },
                        )
            except KeyboardInterrupt:
                # Cancel all remaining pending futures and re-raise.
                for pending_future in future_to_ctx:
                    pending_future.cancel()
                raise

    duration_seconds = time.monotonic() - started
    logger.info(
        "parallel_batch_summary batch_id=%s ok=%s failed=%s duration_ms=%s",
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
