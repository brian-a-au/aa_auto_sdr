"""Compare previous/latest captures, aggregating multi-suite output once."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from aa_auto_sdr.cli.commands import diff as diff_cmd
from aa_auto_sdr.core.exceptions import OutputError, SnapshotError
from aa_auto_sdr.core.exit_codes import ExitCode

logger = logging.getLogger(__name__)


def run(
    *,
    rsids: list[str],
    profile: str | None,
    snapshot_dir: Path | None = None,
    format_name: str | None,
    output: str | None,
    side_by_side: bool = False,
    summary: bool = False,
    ignore_fields: frozenset[str] = frozenset(),
    extended_fields: bool = False,
    quiet: bool = False,
    labels: tuple[str, str] | None = None,
    reverse: bool = False,
    changes_only: bool = False,
    show_only: frozenset[str] = frozenset(),
    max_issues: int | None = None,
    warn_threshold: int | None = None,
    color_theme: str = "default",
) -> int:
    """Run --diff for each RSID: the latest snapshot against its covering baseline.

    The baseline is the newest earlier snapshot whose scope covers the latest
    one (see snapshot/baseline.py), so a filtered snapshot in between never
    hides changes. Labels and logs still read `@previous` / `@latest`."""
    started_ms = time.monotonic()
    logger.info(
        "command_start command=compare_with_prev",
        extra={"command": "compare_with_prev"},
    )
    exit_code = ExitCode.GENERIC.value

    try:
        if not rsids:
            print(
                "error: --compare-with-prev requires at least one positional RSID.",
                flush=True,
                file=sys.stderr,
            )
            exit_code = ExitCode.USAGE.value
            return exit_code

        if len(rsids) >= 2:
            exit_code = _run_multiple(
                rsids=rsids,
                profile=profile,
                snapshot_dir=snapshot_dir,
                format_name=format_name,
                output=output,
                side_by_side=side_by_side,
                summary=summary,
                ignore_fields=ignore_fields,
                extended_fields=extended_fields,
                quiet=quiet,
                labels=labels,
                reverse=reverse,
                changes_only=changes_only,
                show_only=show_only,
                max_issues=max_issues,
                warn_threshold=warn_threshold,
                color_theme=color_theme,
            )
            return exit_code

        worst = ExitCode.OK.value
        for rsid in rsids:
            rc = diff_cmd.run(
                a=f"{rsid}@previous",
                b=f"{rsid}@latest",
                format_name=format_name,
                output=output,
                profile=profile,
                snapshot_dir=snapshot_dir,
                side_by_side=side_by_side,
                summary=summary,
                ignore_fields=ignore_fields,
                extended_fields=extended_fields,
                quiet=quiet,
                labels=labels,
                reverse=reverse,
                changes_only=changes_only,
                show_only=show_only,
                max_issues=max_issues,
                warn_threshold=warn_threshold,
                color_theme=color_theme,
                covering_rsid=rsid,
            )
            worst = max(worst, rc)
        exit_code = worst
        return exit_code

    except OutputError as exc:
        from aa_auto_sdr.output.error_envelope import emit_error_envelope

        exit_code = ExitCode.OUTPUT.value
        emit_error_envelope(exc, exit_code)
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=compare_with_prev exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "compare_with_prev",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _run_multiple(
    *,
    rsids: list[str],
    profile: str | None,
    snapshot_dir: Path | None,
    format_name: str | None,
    output: str | None,
    side_by_side: bool,
    summary: bool,
    ignore_fields: frozenset[str],
    extended_fields: bool,
    quiet: bool,
    labels: tuple[str, str] | None,
    reverse: bool,
    changes_only: bool,
    show_only: frozenset[str],
    max_issues: int | None,
    warn_threshold: int | None,
    color_theme: str,
) -> int:
    from aa_auto_sdr.core import colors

    colors.set_theme(color_theme)
    fmt = format_name or "console"
    if not diff_cmd.validate_output_format(fmt, output):
        return ExitCode.OUTPUT.value
    results = []
    sections = []
    full_reports = []
    for rsid in rsids:
        try:
            report = diff_cmd.compute_report(
                a=f"{rsid}@previous",
                b=f"{rsid}@latest",
                profile=profile,
                snapshot_dir=snapshot_dir,
                reverse=reverse,
                ignore_fields=ignore_fields,
                extended_fields=extended_fields,
                covering_rsid=rsid,
            )
        except SnapshotError as exc:
            code = ExitCode.SNAPSHOT.value
            error = {"error_type": type(exc).__name__, "error": str(exc)}
            results.append({"rsid": rsid, "exit_code": code, "error": error})
            if fmt in ("json", "markdown") and output in (None, "-"):
                from aa_auto_sdr.output.error_envelope import emit_error_envelope

                emit_error_envelope(exc, code)
            else:
                print(f"snapshot error: {exc}", file=sys.stderr, flush=True)
            body = f"{error['error_type']}: {error['error']}\n"
        else:
            code = diff_cmd.report_exit_code(report, warn_threshold)
            body = diff_cmd.render_report(
                report,
                fmt=fmt,
                side_by_side=side_by_side,
                summary=summary,
                quiet=quiet,
                labels=labels,
                changes_only=changes_only,
                show_only=show_only,
                max_issues=max_issues,
                ignore_fields=ignore_fields,
                extended_fields=extended_fields,
                baseline_by_time=False,  # covering baseline: chosen by scope
            )
            result = {"rsid": rsid, "exit_code": code}
            if fmt == "json":
                result["report"] = json.loads(body)
            results.append(result)
            full_reports.append(report)
        if fmt != "json":
            sections.append(f"## {rsid} (exit_code={code})\n\n{body}")
    worst = max(result["exit_code"] for result in results)
    rendered = (
        json.dumps({"schema": "aa-compare-with-prev/v1", "results": results, "exit_code": worst}, indent=2) + "\n"
        if fmt == "json"
        else "\n".join(sections)
    )
    try:
        diff_cmd.write_output(rendered, output)
    except OSError as exc:
        raise OutputError(f"Unable to write previous comparisons to {output or 'stdout'}: {exc}") from exc
    for report in full_reports:
        diff_cmd._maybe_append_step_summary(report, labels=labels)
    return worst
