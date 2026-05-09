"""Batch SDR generation. Dispatches to sequential or parallel runner.

The runner is deliberately small: it doesn't print, it doesn't resolve
identifiers, it just iterates `rsids` and calls `pipeline.single.run_single`,
catching `AaAutoSdrError` subclasses to record per-RSID failures.

Optional `progress_callback(i, total, rsid)` and
`failure_callback(i, total, rsid, message)` let the CLI inject stdout/stderr
behavior without the runner knowing about printing — the runner is testable
without `capsys`."""

from __future__ import annotations

import dataclasses
import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from aa_auto_sdr.api.cache import ValidationCache
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
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult
from aa_auto_sdr.pipeline.workers import run_parallel
from aa_auto_sdr.sdr.builder import ComponentFilter

logger = logging.getLogger(__name__)

# Mirrors the per-exception exit codes in cli/commands/generate.py so a single-
# RSID equivalent invocation would have returned the same code.
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
    total = 0
    for path in result.outputs:
        try:
            total += os.path.getsize(path)
        except OSError:
            # Output file disappeared between write and size-stat; skip.
            continue
    return total


def run_batch(
    *,
    client: AaClient,
    rsids: list[str],
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
    failure_callback: Callable[[int, int, str, str], None] | None = None,
    snapshot_dir: Path | None = None,
    component_filter: ComponentFilter | None = None,
    workers: int = 1,
    fail_fast: bool = False,
    cache: ValidationCache | None = None,
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
) -> BatchResult:
    """Sequential or parallel per-RSID SDR generation. Continue on error.

    workers=1 (default): existing sequential path, byte-equivalent to pre-v1.8.0.
    workers>=2: dispatches to pipeline.workers.run_parallel.

    fail_fast applies only to the parallel path; ignored for workers=1.
    cache is currently a placeholder for v1.12.0's quality engine; passed
    through to workers but unused by the SDR pipeline today.
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if workers == 1:
        return _run_sequential(
            client=client,
            rsids=rsids,
            formats=formats,
            output_dir=output_dir,
            captured_at=captured_at,
            tool_version=tool_version,
            progress_callback=progress_callback,
            failure_callback=failure_callback,
            snapshot_dir=snapshot_dir,
            component_filter=component_filter,
            audit_naming=audit_naming,
            flag_stale=flag_stale,
        )
    return run_parallel(
        rsids=rsids,
        workers=workers,
        client=client,
        cache=cache,
        fail_fast=fail_fast,
        formats=formats,
        output_dir=output_dir,
        captured_at=captured_at,
        tool_version=tool_version,
        snapshot_dir=snapshot_dir,
        component_filter=component_filter,
        progress_callback=progress_callback,
        failure_callback=failure_callback,
        audit_naming=audit_naming,
        flag_stale=flag_stale,
    )


def _run_sequential(
    *,
    client: AaClient,
    rsids: list[str],
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
    failure_callback: Callable[[int, int, str, str], None] | None = None,
    snapshot_dir: Path | None = None,
    component_filter: ComponentFilter | None = None,
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
) -> BatchResult:
    """Sequential per-RSID SDR generation. Continue on error.

    Args:
      rsids: canonical RSIDs (caller is responsible for resolution + dedup).
      progress_callback: optional `(i, total, rsid)` called before each run.
      failure_callback: optional `(i, total, rsid, message)` called on per-RSID failure.

    Returns BatchResult with per-RSID successes, failures, total wall-clock seconds,
    and total output bytes (across successful runs only).
    """
    batch_id = uuid.uuid4().hex[:8]
    successes: list[RunResult] = []
    failures: list[BatchFailure] = []
    total_bytes = 0
    started = time.monotonic()
    total = len(rsids)

    for index, rsid in enumerate(rsids, start=1):
        if progress_callback is not None:
            progress_callback(index, total, rsid)
        run_started = time.monotonic()
        logger.info(
            "rsid_start rsid=%s batch_id=%s (%s/%s)",
            rsid,
            batch_id,
            index,
            total,
            extra={"rsid": rsid, "batch_id": batch_id},
        )
        try:
            result = single.run_single(
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
                },
            )
            if failure_callback is not None:
                failure_callback(index, total, rsid, message)
            failures.append(
                BatchFailure(
                    rsid=rsid,
                    error_type=type(exc).__name__,
                    message=message,
                    exit_code=exit_code,
                ),
            )
            continue
        # Stamp the per-RSID wall-clock onto the RunResult (it's frozen, so
        # re-construct via dataclasses.replace). The banner ✓ row needs this.
        result = dataclasses.replace(result, duration_seconds=time.monotonic() - run_started)
        successes.append(result)
        total_bytes += _bytes_for(result)
        logger.info(
            "rsid_complete rsid=%s batch_id=%s duration_ms=%s count=%s",
            rsid,
            batch_id,
            int(result.duration_seconds * 1000),
            len(result.outputs),
            extra={
                "rsid": rsid,
                "batch_id": batch_id,
                "duration_ms": int(result.duration_seconds * 1000),
                "count": len(result.outputs),
            },
        )

    elapsed = time.monotonic() - started
    logger.info(
        "batch_summary batch_id=%s ok=%s failed=%s duration_ms=%s",
        batch_id,
        len(successes),
        len(failures),
        int(elapsed * 1000),
        extra={
            "batch_id": batch_id,
            "count": len(successes),
            "count_failed": len(failures),
            "duration_ms": int(elapsed * 1000),
        },
    )
    return BatchResult(
        successes=successes,
        failures=failures,
        total_duration_seconds=elapsed,
        total_output_bytes=total_bytes,
        batch_id=batch_id,
    )
