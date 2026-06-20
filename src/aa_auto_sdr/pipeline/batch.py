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
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult
from aa_auto_sdr.pipeline.sampling import sample_rsids
from aa_auto_sdr.pipeline.single import run_single
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
    sample_size: int | None = None,  # v1.10.0
    sample_seed: int | None = None,  # v1.10.0
    sample_stratified: bool = False,  # v1.10.0
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
) -> BatchResult:
    """Sequential or parallel per-RSID SDR generation. Continue on error.

    workers=1 (default): existing sequential path, byte-equivalent to pre-v1.8.0.
    workers>=2: dispatches to pipeline.workers.run_parallel.

    fail_fast applies only to the parallel path; ignored for workers=1.
    cache is currently a placeholder for v1.12.0's quality engine; passed
    through to workers but unused by the SDR pipeline today.

    v1.10.0: when ``sample_size`` is provided and strictly less than
    ``len(rsids)``, the input list is replaced by a sampled subset (random or
    stratified by RSID prefix). Sampling is deterministic given ``sample_seed``.
    The resulting BatchResult records ``sampled``/``sample_size``/
    ``sample_seed``/``total_available`` so banner + JSON consumers can show
    "showing N of M (sampled)".
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")

    if sample_size is not None and sample_size < 1:
        raise ValueError(f"sample_size must be >= 1, got {sample_size}")

    total_available = len(rsids)
    sampled = False
    sample_strategy: str | None = None
    if sample_size is not None and sample_size < total_available:
        rsids = sample_rsids(
            rsids,
            sample_size=sample_size,
            seed=sample_seed,
            stratified=sample_stratified,
        )
        sampled = True
        sample_strategy = "stratified" if sample_stratified else "random"
        logger.info(
            "batch_sampled total_available=%d count=%d seed=%s strategy=%s",
            total_available,
            len(rsids),
            sample_seed,
            sample_strategy,
            extra={
                "count": len(rsids),
                "count_total": total_available,
                "sample_size": sample_size,
                "sample_seed": sample_seed,
                "sample_strategy": sample_strategy,
            },
        )

    if workers == 1:
        inner = _run_sequential(
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
            fail_on_quality=fail_on_quality,
            quality_report=quality_report,
            cache=cache,
            git_commit=git_commit,
            git_push=git_push,
            git_message=git_message,
            template_path=template_path,
            template_organization=template_organization,
            notion_force_new=notion_force_new,
            notion_registry_database=notion_registry_database,
            no_notion_registry=no_notion_registry,
        )
    else:
        inner = run_parallel(
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
        )

    # v1.12.0 — collect per-RSID quality verdicts.
    verdicts: dict[str, str] = {}
    for ok in inner.successes:
        if ok.quality_verdict:
            verdicts[ok.rsid] = ok.quality_verdict

    return dataclasses.replace(
        inner,
        sampled=sampled,
        sample_size=sample_size if sampled else None,
        sample_seed=sample_seed if sampled else None,
        sample_strategy=sample_strategy if sampled else None,
        total_available=total_available,
        quality_verdicts=verdicts,
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
    fail_on_quality: str | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0
    cache: ValidationCache | None = None,  # v1.12.0
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
            from aa_auto_sdr.sdr.quality import SeverityLevel as _SeverityLevel

            _foq = _SeverityLevel(fail_on_quality) if fail_on_quality else None
            result = run_single(
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
                fail_on_quality=_foq,
                quality_report=quality_report,
                cache=cache,
                git_commit=git_commit,
                git_push=git_push,
                git_message=git_message,
                template_path=template_path,
                template_organization=template_organization,
                notion_force_new=notion_force_new,
                notion_registry_database=notion_registry_database,
                no_notion_registry=no_notion_registry,
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
