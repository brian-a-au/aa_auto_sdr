"""diff command — v1.2 surface (quiet, labels, reverse, warn-threshold,
changes-only, show-only, max-issues, $GITHUB_STEP_SUMMARY append)."""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from pathlib import Path

from aa_auto_sdr.core.atomic_io import atomic_write_text
from aa_auto_sdr.core.exceptions import SnapshotError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.profiles import default_base
from aa_auto_sdr.output.diff_renderers._filters import filter_for_render
from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.diff_coverage import diff_coverage
from aa_auto_sdr.snapshot.models import DiffReport
from aa_auto_sdr.snapshot.resolver import is_time_relative_token, resolve_snapshot

logger = logging.getLogger(__name__)

_VALID_FORMATS = ("console", "json", "markdown", "pr-comment")


def run(
    *,
    a: str,
    b: str,
    format_name: str | None,
    output: str | None,
    profile: str | None,
    snapshot_dir: Path | None = None,
    side_by_side: bool = False,
    summary: bool = False,
    ignore_fields: frozenset[str] = frozenset(),
    extended_fields: bool = False,  # v1.9.0
    quiet: bool = False,
    labels: tuple[str, str] | None = None,
    reverse: bool = False,
    changes_only: bool = False,
    show_only: frozenset[str] = frozenset(),
    max_issues: int | None = None,
    warn_threshold: int | None = None,
    color_theme: str = "default",
    covering_rsid: str | None = None,
) -> int:
    started_ms = time.monotonic()
    logger.info("command_start command=diff", extra={"command": "diff"})
    exit_code = ExitCode.GENERIC.value
    try:
        from aa_auto_sdr.core import colors

        colors.set_theme(color_theme)
        fmt = format_name or "console"
        if not validate_output_format(fmt, output):
            exit_code = ExitCode.OUTPUT.value
            return exit_code

        try:
            full_report = compute_report(
                a=a,
                b=b,
                profile=profile,
                snapshot_dir=snapshot_dir,
                reverse=reverse,
                ignore_fields=ignore_fields,
                extended_fields=extended_fields,
                covering_rsid=covering_rsid,
            )
        except SnapshotError as exc:
            # `output is None` also renders to stdout (see the write below), so
            # machine formats get the JSON envelope for implicit stdout too —
            # otherwise a human error line lands in the stream a jq consumer
            # is parsing.
            if fmt in ("json", "markdown") and (output is None or output == "-"):
                from aa_auto_sdr.output.error_envelope import emit_error_envelope

                emit_error_envelope(exc, ExitCode.SNAPSHOT.value)
            else:
                print(f"snapshot error: {exc}", file=sys.stderr, flush=True)
            exit_code = ExitCode.SNAPSHOT.value
            return exit_code

        # Color follows stdout's TTY state; text bound for a file must not
        # carry escape codes even when stdout is a terminal.
        to_file = output is not None and output != "-"
        with colors.disabled() if to_file else contextlib.nullcontext():
            rendered = render_report(
                full_report,
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
                # A covering baseline (--compare-with-prev) is chosen by scope, not time.
                baseline_by_time=covering_rsid is None and (is_time_relative_token(a) or is_time_relative_token(b)),
            )
        if to_file:
            try:
                write_output(rendered, output)
            except OSError as exc:
                print(f"error: could not write {output}: {exc}", file=sys.stderr, flush=True)
                exit_code = ExitCode.OUTPUT.value
                return exit_code
        else:
            write_output(rendered, output)

        # GitHub Actions: when GITHUB_STEP_SUMMARY is set, append a markdown view
        # using the FULL report (no presentational filters) so CI surfaces are
        # never misleadingly trimmed.
        _maybe_append_step_summary(full_report, labels=labels)

        if report_exit_code(full_report, warn_threshold) == ExitCode.WARN.value:
            exit_code = ExitCode.WARN.value
            return exit_code
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=diff exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "diff",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _maybe_append_step_summary(
    report: DiffReport,
    *,
    labels: tuple[str, str] | None,
) -> None:
    """If $GITHUB_STEP_SUMMARY is set (CI), append a markdown render to it."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    rendered_md = render_markdown(report, labels=labels)
    try:
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write("\n" + rendered_md + "\n")
    except OSError:
        # Don't fail the diff if step-summary write fails; CI surface is best-effort.
        pass


def compute_report(
    *,
    a: str,
    b: str,
    profile: str | None,
    snapshot_dir: Path | None,
    reverse: bool,
    ignore_fields: frozenset[str],
    extended_fields: bool,
    covering_rsid: str | None = None,
) -> DiffReport:
    """Resolve and compare without presentation or output side effects.

    With `covering_rsid` (used by --compare-with-prev), `a` / `b` are ignored:
    the latest snapshot is compared against the newest earlier snapshot whose
    scope covers it, and the skipped snapshots land in `baseline_skipped`."""
    directory = snapshot_dir or (default_base() / "orgs" / profile / "snapshots" if profile else None)
    if covering_rsid is not None:
        from dataclasses import replace

        from aa_auto_sdr.snapshot.resolver import resolve_covering_pair

        pair = resolve_covering_pair(covering_rsid, snapshot_dir=directory)
        env_a, env_b = (pair.target, pair.baseline) if reverse else (pair.baseline, pair.target)
        report = compare(env_a, env_b, ignore_fields=ignore_fields, extended_fields=extended_fields)
        return replace(report, baseline_skipped=list(pair.skipped))
    if reverse:
        a, b = b, a
    repo_root = Path.cwd()
    env_a = resolve_snapshot(a, profile_snapshot_dir=directory, repo_root=repo_root)
    env_b = resolve_snapshot(b, profile_snapshot_dir=directory, repo_root=repo_root)
    return compare(env_a, env_b, ignore_fields=ignore_fields, extended_fields=extended_fields)


def report_exit_code(report: DiffReport, warn_threshold: int | None) -> int:
    """Evaluate the threshold against the full, unsuppressed comparison."""
    total = sum(len(c.added) + len(c.removed) + len(c.modified) for c in report.components if not c.suppressed)
    return ExitCode.WARN.value if warn_threshold is not None and total >= warn_threshold else ExitCode.OK.value


def render_report(
    full_report: DiffReport,
    *,
    fmt: str,
    side_by_side: bool = False,
    summary: bool = False,
    quiet: bool = False,
    labels: tuple[str, str] | None = None,
    changes_only: bool = False,
    show_only: frozenset[str] = frozenset(),
    max_issues: int | None = None,
    ignore_fields: frozenset[str] = frozenset(),
    extended_fields: bool = False,
    baseline_by_time: bool = False,
) -> str:
    """Apply presentation flags to a copy, preserving the complete report.

    JSON gains a `coverage` object built from the full report and the
    compare options, so it describes the whole comparison, not the filtered view."""
    report = filter_for_render(full_report, changes_only=changes_only, show_only=show_only, max_issues=max_issues)
    if fmt == "json":
        coverage = diff_coverage(
            full_report,
            ignore_fields=ignore_fields,
            extended_fields=extended_fields,
            show_only=show_only,
            baseline_by_time=baseline_by_time,
        )
        return render_json(report, summary=summary, labels=labels, coverage=coverage)
    if fmt == "pr-comment":
        return render_pr_comment(report, summary=summary, labels=labels)
    renderer = render_console if fmt == "console" else render_markdown
    return renderer(report, side_by_side=side_by_side, summary=summary, quiet=quiet, labels=labels)


def write_output(rendered: str, output: str | None) -> None:
    """Emit one complete result, replacing file destinations atomically."""
    if output is None or output == "-":
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Renderers emit glyphs (📊, ⚠, —) and user-authored names; the
        # locale default (cp1252 on Windows) cannot encode them.
        atomic_write_text(target, rendered, encoding="utf-8")
        print(f"wrote: {target}", flush=True)


def validate_output_format(fmt: str, output: str | None) -> bool:
    if fmt not in _VALID_FORMATS:
        print(
            f"error: format '{fmt}' is not available for --diff (use console|json|markdown|pr-comment)",
            file=sys.stderr,
            flush=True,
        )
        return False
    if fmt == "console" and output == "-":
        print(
            "error: --format console cannot pipe to stdout (use --format json|markdown for pipes)",
            file=sys.stderr,
            flush=True,
        )
        return False

    return True
