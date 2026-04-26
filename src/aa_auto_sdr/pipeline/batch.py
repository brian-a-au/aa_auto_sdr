"""Sequential batch SDR generation. Continue-on-error.

The runner is deliberately small: it doesn't print, it doesn't resolve
identifiers, it just iterates `rsids` and calls `pipeline.single.run_single`,
catching `AaAutoSdrError` subclasses to record per-RSID failures.

Optional `progress_callback(i, total, rsid)` and
`failure_callback(i, total, rsid, message)` let the CLI inject stdout/stderr
behavior without the runner knowing about printing — the runner is testable
without `capsys`."""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import Callable
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
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult

# Mirrors the per-exception exit codes in cli/commands/generate.py so a single-
# RSID equivalent invocation would have returned the same code.
_EXIT_CODE_BY_TYPE: dict[type[AaAutoSdrError], int] = {
    ConfigError: 10,
    AuthError: 11,
    ApiError: 12,
    ReportSuiteNotFoundError: 13,
    OutputError: 15,
}


def _exit_code_for(exc: AaAutoSdrError) -> int:
    """Match generate.py's exit-code policy. Most-specific class wins; fallback = 1."""
    for cls in type(exc).__mro__:
        if cls in _EXIT_CODE_BY_TYPE:
            return _EXIT_CODE_BY_TYPE[cls]
    return 1


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
) -> BatchResult:
    """Sequential per-RSID SDR generation. Continue on error.

    Args:
      rsids: canonical RSIDs (caller is responsible for resolution + dedup).
      progress_callback: optional `(i, total, rsid)` called before each run.
      failure_callback: optional `(i, total, rsid, message)` called on per-RSID failure.

    Returns BatchResult with per-RSID successes, failures, total wall-clock seconds,
    and total output bytes (across successful runs only).
    """
    successes: list[RunResult] = []
    failures: list[BatchFailure] = []
    total_bytes = 0
    started = time.monotonic()
    total = len(rsids)

    for index, rsid in enumerate(rsids, start=1):
        if progress_callback is not None:
            progress_callback(index, total, rsid)
        run_started = time.monotonic()
        try:
            result = single.run_single(
                client=client,
                rsid=rsid,
                formats=formats,
                output_dir=output_dir,
                captured_at=captured_at,
                tool_version=tool_version,
            )
        except AaAutoSdrError as exc:
            message = str(exc)
            if failure_callback is not None:
                failure_callback(index, total, rsid, message)
            failures.append(
                BatchFailure(
                    rsid=rsid,
                    error_type=type(exc).__name__,
                    message=message,
                    exit_code=_exit_code_for(exc),
                ),
            )
            continue
        # Stamp the per-RSID wall-clock onto the RunResult (it's frozen, so
        # re-construct via dataclasses.replace). The banner ✓ row needs this.
        result = dataclasses.replace(result, duration_seconds=time.monotonic() - run_started)
        successes.append(result)
        total_bytes += _bytes_for(result)

    elapsed = time.monotonic() - started
    return BatchResult(
        successes=successes,
        failures=failures,
        total_duration_seconds=elapsed,
        total_output_bytes=total_bytes,
    )
