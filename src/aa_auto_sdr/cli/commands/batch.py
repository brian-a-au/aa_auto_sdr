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

import os
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import colors, credentials
from aa_auto_sdr.core.constants import BANNER_WIDTH
from aa_auto_sdr.core.exceptions import (
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.version import __version__
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline import batch as batch_runner
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult

from aa_auto_sdr.core.exit_codes import ExitCode


def run(
    *,
    rsids: list[str],
    output_dir: Path,
    format_name: str,
    profile: str | None,
    snapshot: bool = False,
) -> int:
    """Entry point for `--batch RSID1 RSID2 ...`.

    `rsids` here is the raw list from argparse; identifier resolution + dedup
    happen below before `run_batch` sees the list.
    """
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.CONFIG.value

    snapshot_dir: Path | None = None
    if snapshot:
        if not profile:
            print(
                "error: --snapshot requires --profile (snapshots are profile-scoped)",
                flush=True,
            )
            return ExitCode.CONFIG.value
        from aa_auto_sdr.core.profiles import default_base

        snapshot_dir = default_base() / "orgs" / profile / "snapshots"

    print(f"using credentials from: {creds.source}")

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
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return ExitCode.AUTH.value

    # Identifier resolution: print a one-line `error: ...` immediately on
    # failure (matches single-RSID generate.py convention) AND collect the
    # failure for the rolled-up summary banner. Successes accumulate canonically
    # de-duped (so passing a name + its RSID doesn't generate twice).
    canonical: list[str] = []
    seen: set[str] = set()
    pre_failures: list[BatchFailure] = []
    for identifier in rsids:
        try:
            resolved, _was_name = fetch.resolve_rsid(client, identifier)
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

    def _on_progress(i: int, total: int, rsid: str) -> None:
        print(f"[{i}/{total}] generating {rsid}...", flush=True)

    def _on_failure(i: int, total: int, rsid: str, message: str) -> None:
        print(f"[{i}/{total}] {rsid}: FAILED — {message}", flush=True)

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
    final = BatchResult(
        successes=result.successes,
        failures=all_failures,
        total_duration_seconds=result.total_duration_seconds,
        total_output_bytes=result.total_output_bytes,
    )

    _print_summary(final)

    if not final.failures:
        return ExitCode.OK.value
    if final.successes:
        return ExitCode.PARTIAL_SUCCESS.value
    # All failed → exit code of the *last* failure
    return final.failures[-1].exit_code


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
