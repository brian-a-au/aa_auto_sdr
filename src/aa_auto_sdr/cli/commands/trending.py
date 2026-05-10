"""--trending-window handler: per-RSID drift window over snapshot files.

Reads existing snapshots (no AA API contact). Resolves snapshot directory
from --snapshot-dir or active profile. Validates duration via parse_duration.
Calls compute_trending() once per RSID; renders all reports together.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.snapshot._duration import parse_duration
from aa_auto_sdr.snapshot.trending import TrendingReport, WindowSpec, compute_trending

logger = logging.getLogger(__name__)

_VALID_FORMATS = ("console", "json", "markdown")


def run(
    *,
    rsids: list[str],
    duration: str,
    snapshot_dir: Path | None,
    profile: str | None,
    format_name: str | None,
    output: str | None,
    extended_fields: bool = False,
    ignore_fields: tuple[str, ...] = (),
) -> int:
    """Entry point for `--trending-window`.

    Returns ExitCode.OK on success, USAGE for argument errors, CONFIG when
    no snapshot directory can be resolved, NOT_FOUND when no RSID has any
    snapshots in the window, OUTPUT for unknown format / write failure.
    """
    started_ms = time.monotonic()
    logger.info("command_start command=trending", extra={"command": "trending"})
    exit_code = ExitCode.GENERIC.value

    try:
        if not rsids:
            print(
                "error: --trending-window requires at least one positional RSID.",
                flush=True,
            )
            exit_code = ExitCode.USAGE.value
            return exit_code

        try:
            delta = parse_duration(duration)
        except ValueError as exc:
            print(f"error: {exc}", flush=True)
            exit_code = ExitCode.USAGE.value
            return exit_code

        fmt = format_name or "console"
        if fmt not in _VALID_FORMATS:
            print(
                f"error: --trending-window format must be {'|'.join(_VALID_FORMATS)} (got '{fmt}')",
                flush=True,
            )
            exit_code = ExitCode.OUTPUT.value
            return exit_code

        # Resolve snapshot dir.
        snap_dir = _resolve_snapshot_dir(snapshot_dir=snapshot_dir, profile=profile)
        if snap_dir is None:
            print(
                "error: --trending-window requires a snapshot directory. "
                "Set --snapshot-dir or activate a profile that has snapshots configured.",
                flush=True,
            )
            exit_code = ExitCode.CONFIG.value
            return exit_code

        end_at = datetime.now(UTC)
        start_at = end_at - delta
        window = WindowSpec(duration=duration, start_at=start_at, end_at=end_at)
        logger.info(
            "trending_window_resolved duration=%s start_at=%s end_at=%s",
            duration,
            start_at.isoformat(),
            end_at.isoformat(),
            extra={
                "duration": duration,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
            },
        )

        # Compute one TrendingReport per RSID.
        reports: list[TrendingReport] = []
        empty_rsids: list[str] = []
        for rsid in rsids:
            report = compute_trending(
                snapshot_dir=snap_dir,
                rsid=rsid,
                window=window,
                extended_fields=extended_fields,
                ignore_fields=ignore_fields,
            )
            if not report.series:
                empty_rsids.append(rsid)
            reports.append(report)

        # Render.
        rendered = _render(reports, fmt=fmt)

        if output is None or output == "-":
            sys.stdout.write(rendered)
        else:
            Path(output).write_text(rendered)

        # Decide exit code based on per-RSID series presence.
        if len(empty_rsids) == len(rsids) and rsids:
            print(
                f"warning: no snapshots found in window for any RSID: {empty_rsids}",
                file=sys.stderr,
            )
            exit_code = ExitCode.NOT_FOUND.value
        elif empty_rsids:
            print(
                f"warning: no snapshots found in window for: {empty_rsids}",
                file=sys.stderr,
            )
            exit_code = ExitCode.PARTIAL_SUCCESS.value
        else:
            exit_code = ExitCode.OK.value
        return exit_code

    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=trending exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "trending",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _resolve_snapshot_dir(*, snapshot_dir: Path | None, profile: str | None) -> Path | None:
    """Resolve snapshot directory: CLI flag → profile → None.

    Profile path convention `default_base() / "orgs" / <profile> / "snapshots"`
    matches the existing pattern in `cli/commands/diff.py` and
    `cli/commands/snapshots.py`. Returning the path unconditionally
    (even if the directory doesn't exist on disk yet) is fine because
    `list_snapshots` handles missing dirs by returning an empty list.
    """
    if snapshot_dir is not None:
        return snapshot_dir
    if profile is not None:
        from aa_auto_sdr.core.profiles import default_base

        return default_base() / "orgs" / profile / "snapshots"
    return None


def _render(reports: list[TrendingReport], *, fmt: str) -> str:
    if fmt == "json":
        from aa_auto_sdr.output.trending_renderers.json import render_json

        return render_json(reports)
    if fmt == "markdown":
        from aa_auto_sdr.output.trending_renderers.markdown import render_markdown

        return render_markdown(reports)
    from aa_auto_sdr.output.trending_renderers.console import render_console

    return render_console(reports)
