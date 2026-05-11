"""batch command: resolve+dedup identifiers → pipeline.run_batch → summary banner.

The runner in pipeline/batch.py is pure; this module owns all stdout printing
(per-RSID progress lines + the CJA-style summary banner). Exit codes:

  0   all RSIDs succeeded
  10  missing/invalid credentials (ConfigError)
  11  AA OAuth Server-to-Server failure (AuthError)
  14  partial success — some RSIDs ok, some failed (PARTIAL_SUCCESS)
  15  --output - rejected for batch (handled in cli/main.py before dispatch)
  *   all failed — exit code of the *last* failure (so scripts see a real failure mode)
"""

from __future__ import annotations

import dataclasses
import json as _json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.cache import ValidationCache
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.core import colors, credentials, timings
from aa_auto_sdr.core.constants import BANNER_WIDTH
from aa_auto_sdr.core.exceptions import (
    AmbiguousMatchError,
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.run_summary import PerRsidResult, RunSummary
from aa_auto_sdr.core.version import __version__
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline import batch as batch_runner
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult

logger = logging.getLogger(__name__)


def _emit_timings_if_enabled(*, show_timings: bool) -> None:
    if not show_timings:
        return
    import sys as _sys

    _sys.stderr.write(timings.format_report())
    _sys.stderr.flush()
    timings.disable()


def _emit_run_summary(
    *,
    run_summary_json: str | None,
    started_at: datetime,
    finished_at: datetime,
    profile: str | None,
    per_rsid: list[PerRsidResult],
    show_timings: bool,
    batch_result: BatchResult | None = None,
) -> None:
    if not run_summary_json:
        return
    summary = RunSummary(
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=(finished_at - started_at).total_seconds(),
        tool_version=__version__,
        profile=profile,
        rsids=per_rsid,
        timings=timings.report() if show_timings else [],
        sampled=batch_result.sampled if batch_result is not None else False,
        sample_size=batch_result.sample_size if batch_result is not None else None,
        sample_seed=batch_result.sample_seed if batch_result is not None else None,
        sample_strategy=batch_result.sample_strategy if batch_result is not None else None,
        total_available=batch_result.total_available if batch_result is not None else 0,
    )
    if run_summary_json == "-":
        # Compact single-line JSON on stdout — easier to consume from scripts and
        # plays nicely with `splitlines()[-1]` shaped pipelines.
        payload = _json.dumps(summary.to_dict(), sort_keys=True)
        import sys as _sys

        _sys.stdout.write(payload + "\n")
        _sys.stdout.flush()
    else:
        payload = _json.dumps(summary.to_dict(), sort_keys=True, indent=2)
        Path(run_summary_json).write_text(payload + "\n")
        print(f"wrote run summary: {run_summary_json}", flush=True)


def run(
    *,
    rsids: list[str],
    output_dir: Path,
    format_name: str,
    profile: str | None,
    snapshot: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    keep_last: int | None = None,
    keep_since: str | None = None,
    metrics_only: bool = False,  # v1.2
    dimensions_only: bool = False,  # v1.2
    dry_run: bool = False,  # v1.2 — preview-only; no component fetch, no writes
    open_after: bool = False,  # v1.2 — open output_dir in OS default app
    assume_yes: bool = False,  # v1.2; accepted for parity, not currently consumed
    show_timings: bool = False,  # v1.2.1
    run_summary_json: str | None = None,  # v1.2.1
    retry_policy: RetryPolicy | None = None,  # v1.7.0 — shared retry budget
    workers: int = 1,  # v1.8.0 — parallel workers for --batch
    fail_fast: bool = False,  # v1.8.0 — cancel pending workers on first failure
    enable_cache: bool = False,  # v1.8.0 — instantiate ValidationCache
    clear_cache: bool = False,  # v1.8.0 — clear cache at run start
    cache_ttl: int = 3600,  # v1.8.0 — cache TTL in seconds
    cache_size: int = 1000,  # v1.8.0 — cache LRU max-size
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
    name_match: str = "insensitive",  # v1.9.0
    sample_size: int | None = None,  # v1.10.0
    sample_seed: int | None = None,  # v1.10.0
    sample_stratified: bool = False,  # v1.10.0
    fail_on_quality: str | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0
    # v1.15.0 — git integration
    git_commit: bool = False,
    git_push: bool = False,
    git_message: str | None = None,
) -> int:
    """Pattern 9B.1 wrapper: emit command_start/command_complete around the
    real body in ``_run_impl`` so all the existing early returns flow
    through without restructuring."""
    started_ms = time.monotonic()
    logger.info("command_start command=batch", extra={"command": "batch"})
    exit_code = ExitCode.GENERIC.value
    try:
        exit_code = _run_impl(
            rsids=rsids,
            output_dir=output_dir,
            format_name=format_name,
            profile=profile,
            snapshot=snapshot,
            auto_snapshot=auto_snapshot,
            auto_prune=auto_prune,
            keep_last=keep_last,
            keep_since=keep_since,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            dry_run=dry_run,
            open_after=open_after,
            assume_yes=assume_yes,
            show_timings=show_timings,
            run_summary_json=run_summary_json,
            retry_policy=retry_policy,
            workers=workers,
            fail_fast=fail_fast,
            enable_cache=enable_cache,
            clear_cache=clear_cache,
            cache_ttl=cache_ttl,
            cache_size=cache_size,
            audit_naming=audit_naming,
            flag_stale=flag_stale,
            name_match=name_match,
            sample_size=sample_size,
            sample_seed=sample_seed,
            sample_stratified=sample_stratified,
            fail_on_quality=fail_on_quality,
            quality_report=quality_report,
            git_commit=git_commit,
            git_push=git_push,
            git_message=git_message,
        )
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=batch exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "batch",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _run_impl(
    *,
    rsids: list[str],
    output_dir: Path,
    format_name: str,
    profile: str | None,
    snapshot: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    keep_last: int | None = None,
    keep_since: str | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    dry_run: bool = False,
    open_after: bool = False,
    assume_yes: bool = False,  # noqa: ARG001 — accepted for parity, not currently consumed
    show_timings: bool = False,
    run_summary_json: str | None = None,
    retry_policy: RetryPolicy | None = None,
    workers: int = 1,
    fail_fast: bool = False,
    enable_cache: bool = False,
    clear_cache: bool = False,
    cache_ttl: int = 3600,
    cache_size: int = 1000,
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
    name_match: str = "insensitive",  # v1.9.0
    sample_size: int | None = None,  # v1.10.0
    sample_seed: int | None = None,  # v1.10.0
    sample_stratified: bool = False,  # v1.10.0
    fail_on_quality: str | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0
    # v1.15.0 — git integration
    git_commit: bool = False,
    git_push: bool = False,
    git_message: str | None = None,
) -> int:
    """Entry point body for `--batch RSID1 RSID2 ...`.

    `rsids` here is the raw list from argparse; identifier resolution + dedup
    happen below before `run_batch` sees the list.
    """
    started_at = datetime.now(UTC)

    if show_timings:
        timings.clear()
        timings.enable()

    if metrics_only and dimensions_only:
        print(
            "error: --metrics-only and --dimensions-only are mutually exclusive",
            flush=True,
        )
        return ExitCode.USAGE.value

    if (metrics_only or dimensions_only) and (snapshot or auto_snapshot):
        print(
            "error: --metrics-only / --dimensions-only cannot be combined with "
            "--snapshot / --auto-snapshot — filtered snapshots produce misleading diffs",
            flush=True,
        )
        return ExitCode.USAGE.value

    from aa_auto_sdr.sdr.builder import ComponentFilter

    component_filter = ComponentFilter.from_args(
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
    )

    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.CONFIG.value

    snapshot_dir: Path | None = None
    save_required = snapshot or auto_snapshot
    if save_required:
        if not profile:
            flag = "--snapshot" if snapshot else "--auto-snapshot"
            print(
                f"error: {flag} requires --profile (snapshots are profile-scoped)",
                flush=True,
            )
            return ExitCode.CONFIG.value
        from aa_auto_sdr.core.profiles import default_base

        snapshot_dir = default_base() / "orgs" / profile / "snapshots"

    try:
        formats = registry.resolve_formats(format_name or "excel")
    except KeyError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.GENERIC.value

    registry.bootstrap()
    for fmt in formats:
        try:
            registry.get_writer(fmt)
        except KeyError:
            print(f"error: format '{fmt}' is not available in this build", flush=True)
            return ExitCode.OUTPUT.value

    try:
        with timings.Timer("auth"):
            client = AaClient.from_credentials(creds, retry_policy=retry_policy)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        _emit_timings_if_enabled(show_timings=show_timings)
        return ExitCode.AUTH.value

    # Identifier resolution: print a one-line `error: ...` immediately on
    # failure (matches single-RSID generate.py convention) AND collect the
    # failure for the rolled-up summary banner. Successes accumulate canonically
    # de-duped (so passing a name + its RSID doesn't generate twice).
    canonical: list[str] = []
    seen: set[str] = set()
    pre_failures: list[BatchFailure] = []
    with timings.Timer("resolve"):
        for identifier in rsids:
            try:
                resolved, _was_name = fetch.resolve_rsid(client, identifier, name_match=name_match)
            except AmbiguousMatchError as exc:
                print(
                    f"error: identifier '{identifier}' is ambiguous; matched {len(exc.candidates)} report suites:",
                    file=sys.stderr,
                )
                for cand_rsid, cand_name in exc.candidates:
                    print(f"  - {cand_rsid}  ({cand_name})", file=sys.stderr)
                print(
                    "Use a more specific identifier or pass `--name-match exact` (or the rsid directly).",
                    file=sys.stderr,
                )
                pre_failures.append(
                    BatchFailure(
                        rsid=identifier,
                        error_type=type(exc).__name__,
                        message=str(exc),
                        exit_code=ExitCode.NOT_FOUND.value,
                    ),
                )
                continue
            except ReportSuiteNotFoundError as exc:
                print(f"error: {exc}", flush=True)
                pre_failures.append(
                    BatchFailure(
                        rsid=identifier,
                        error_type=type(exc).__name__,
                        message=str(exc),
                        exit_code=ExitCode.NOT_FOUND.value,
                    ),
                )
                continue
            except ApiError as exc:
                print(f"api error: {exc}", flush=True)
                pre_failures.append(
                    BatchFailure(
                        rsid=identifier,
                        error_type=type(exc).__name__,
                        message=str(exc),
                        exit_code=ExitCode.API.value,
                    ),
                )
                continue
            for rs in resolved:
                if rs in seen:
                    continue
                seen.add(rs)
                canonical.append(rs)

    captured_at = datetime.now(UTC)

    if dry_run:
        # Preview-only path (v1.2): credentials resolved + auth round-trip done +
        # all identifiers resolved → list what would be written per RSID and
        # exit. No component fetches, no file writes, no snapshot writes. We
        # surface any pre-resolution failures already printed above as part of
        # the dry-run report by listing canonical RSIDs only — unresolved
        # identifiers were already reported with `error: ...` lines above.
        print("DRY RUN — would generate:", flush=True)
        ext_map = {
            "excel": "xlsx",
            "json": "json",
            "html": "html",
            "markdown": "md",
            "csv": "csv",
        }
        for canonical_rsid in canonical:
            for fmt in formats:
                if fmt == "csv":
                    print(f"  {output_dir / f'{canonical_rsid}.<component>.csv'}")
                else:
                    ext = ext_map.get(fmt, fmt)
                    print(f"  {output_dir / f'{canonical_rsid}.{ext}'}")
            if save_required and snapshot_dir is not None:
                from aa_auto_sdr.snapshot.store import snapshot_path

                snap_path = snapshot_path(
                    snapshot_dir=snapshot_dir,
                    rsid=canonical_rsid,
                    captured_at_iso=captured_at.isoformat(),
                )
                print(f"  {snap_path}")
        print("(no files were written; remove --dry-run to execute)", flush=True)
        dry_per_rsid: list[PerRsidResult] = [
            PerRsidResult(
                rsid=rs,
                name=None,
                succeeded=True,
                formats=list(formats),
                output_paths=[],
                snapshot_path=None,
                error=None,
            )
            for rs in canonical
        ]
        dry_per_rsid.extend(
            PerRsidResult(
                rsid=bad.rsid,
                name=None,
                succeeded=False,
                formats=list(formats),
                output_paths=[],
                snapshot_path=None,
                error=f"{bad.error_type}: {bad.message}",
            )
            for bad in pre_failures
        )
        _emit_run_summary(
            run_summary_json=run_summary_json,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            profile=profile,
            per_rsid=dry_per_rsid,
            show_timings=show_timings,
        )
        _emit_timings_if_enabled(show_timings=show_timings)
        return ExitCode.OK.value

    def _on_progress(i: int, total: int, rsid: str) -> None:
        print(f"[{i}/{total}] generating {rsid}...", flush=True)

    def _on_failure(i: int, total: int, rsid: str, message: str) -> None:
        print(f"[{i}/{total}] {rsid}: FAILED — {message}", flush=True)

    cache: ValidationCache | None = None
    if enable_cache:
        cache = ValidationCache(
            max_size=cache_size,
            ttl_seconds=cache_ttl,
        )
        if clear_cache:
            cache.clear()

    if canonical:
        result = batch_runner.run_batch(
            client=client,
            rsids=canonical,
            formats=formats,
            output_dir=output_dir,
            captured_at=captured_at,
            tool_version=__version__,
            progress_callback=_on_progress,
            failure_callback=_on_failure,
            snapshot_dir=snapshot_dir,
            component_filter=component_filter,
            workers=workers,
            fail_fast=fail_fast,
            cache=cache,
            audit_naming=audit_naming,
            flag_stale=flag_stale,
            sample_size=sample_size,
            sample_seed=sample_seed,
            sample_stratified=sample_stratified,
            fail_on_quality=fail_on_quality,
            quality_report=quality_report,
            git_commit=git_commit,
            git_push=git_push,
            git_message=git_message,
        )
    else:
        # All identifiers failed to resolve — make an empty BatchResult so the
        # summary banner still prints with the pre-failures rolled in.
        result = BatchResult(
            successes=[],
            failures=[],
            total_duration_seconds=0.0,
            total_output_bytes=0,
        )

    all_failures = list(result.failures) + pre_failures
    final = dataclasses.replace(result, failures=all_failures)

    _print_summary(final)

    per_rsid_results: list[PerRsidResult] = [
        PerRsidResult(
            rsid=ok.rsid,
            name=ok.report_suite_name,
            succeeded=True,
            formats=list(formats),
            output_paths=[str(p) for p in ok.outputs],
            snapshot_path=None,
            error=None,
        )
        for ok in final.successes
    ]
    per_rsid_results.extend(
        PerRsidResult(
            rsid=bad.rsid,
            name=None,
            succeeded=False,
            formats=list(formats),
            output_paths=[],
            snapshot_path=None,
            error=f"{bad.error_type}: {bad.message}",
        )
        for bad in final.failures
    )
    _emit_run_summary(
        run_summary_json=run_summary_json,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        profile=profile,
        per_rsid=per_rsid_results,
        show_timings=show_timings,
        batch_result=final,
    )

    if auto_prune and snapshot_dir is not None:
        rc = _apply_auto_prune(
            snapshot_dir=snapshot_dir,
            rsids=[ok.rsid for ok in final.successes],
            keep_last=keep_last,
            keep_since=keep_since,
        )
        if rc != ExitCode.OK.value:
            _emit_timings_if_enabled(show_timings=show_timings)
            return rc

    if open_after and not dry_run:
        from aa_auto_sdr.core._open import os_open

        os_open(output_dir)

    _emit_timings_if_enabled(show_timings=show_timings)

    # v1.12.0 — batch quality-gate evaluation. Per spec §3.10:
    #   PARTIAL_SUCCESS (14) outranks QUALITY (17). Build failures are more
    #   actionable than quality verdicts. Only when all RSIDs succeed AND at
    #   least one breached do we surface QUALITY.
    if not final.failures:
        if fail_on_quality and any(v == "fail" for v in final.quality_verdicts.values()):
            return ExitCode.QUALITY.value
        return ExitCode.OK.value
    if final.successes:
        return ExitCode.PARTIAL_SUCCESS.value
    # All failed → exit code of the *last* failure
    return final.failures[-1].exit_code


def _apply_auto_prune(
    *,
    snapshot_dir: Path,
    rsids: list[str],
    keep_last: int | None,
    keep_since: str | None,
) -> int:
    """Parse retention policy and prune each RSID under `snapshot_dir`.

    Per-RSID prune failures log a warning but don't abort the batch.
    Returns ExitCode.OK on success, ExitCode.CONFIG on bad/empty policy.
    """
    from aa_auto_sdr.snapshot.retention import parse_policy
    from aa_auto_sdr.snapshot.store import prune_snapshots

    try:
        policy = parse_policy(keep_last=keep_last, keep_since=keep_since)
    except ConfigError as exc:
        print(f"error: {exc}", flush=True)
        return ExitCode.CONFIG.value
    if not policy.is_active():
        print(
            "error: --auto-prune requires --keep-last or --keep-since",
            flush=True,
        )
        return ExitCode.CONFIG.value
    for rs in rsids:
        try:
            prune_snapshots(snapshot_dir, policy, rsid=rs)
        except OSError as exc:
            logger.warning(
                "prune failed rsid=%s error_class=%s",
                rs,
                type(exc).__name__,
                extra={"rsid": rs, "error_class": type(exc).__name__},
            )
    return ExitCode.OK.value


def _print_summary(result: BatchResult) -> None:
    """CJA-style summary banner. See spec §5."""
    total = len(result.successes) + len(result.failures)
    successful = len(result.successes)
    failed = len(result.failures)
    rate = (successful / total * 100) if total else 0.0

    print()
    print("=" * BANNER_WIDTH)
    print(colors.bold("BATCH PROCESSING SUMMARY"))
    print("=" * BANNER_WIDTH)
    print(f"Total report suites: {total}")
    if result.sampled:
        seed_segment = f", seed={result.sample_seed}" if result.sample_seed is not None else ""
        strategy = result.sample_strategy or "random"
        print(f"Sampled {result.sample_size} of {result.total_available} RSIDs (strategy={strategy}{seed_segment})")
    print(f"Successful: {colors.success(str(successful))}")
    print(f"Failed: {colors.error(str(failed))}")
    print(f"Success rate: {colors.status(rate == 100, f'{rate:.1f}%')}")
    print(f"Total output size: {_humanize_bytes(result.total_output_bytes)}")
    print(f"Total duration: {result.total_duration_seconds:.1f}s")
    if total:
        per = result.total_duration_seconds / total
        print(f"Average per report suite: {per:.2f}s")
        if result.total_duration_seconds > 0:
            throughput = total / result.total_duration_seconds
            print(f"Throughput: {throughput:.2f} RSes/second")

    if result.successes:
        print()
        print(colors.bold("Successful Report Suites:"))
        for ok in result.successes:
            label = ok.rsid
            if ok.report_suite_name and ok.report_suite_name != ok.rsid:
                label = f"{ok.rsid} ({ok.report_suite_name})"
            file_count = len(ok.outputs)
            size = _bytes_for_run(ok)
            print(
                f"  {colors.success('✓')} {label} → "
                f"{file_count} files, {_humanize_bytes(size)}, {ok.duration_seconds:.1f}s",
            )

    if result.failures:
        print()
        print(colors.bold("Failed Report Suites:"))
        for bad in result.failures:
            print(f"  {colors.error('✗')} {bad.rsid} — {bad.error_type}: {bad.message}")

    print()
    print("=" * BANNER_WIDTH)


def _bytes_for_run(result: RunResult) -> int:
    total = 0
    for path in result.outputs:
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return total


def _humanize_bytes(n: int) -> str:
    """Render a byte count as B / KB / MB. Mirrors CJA's banner."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"
