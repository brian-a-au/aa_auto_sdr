"""diff command — v1.2 surface (quiet, labels, reverse, warn-threshold,
changes-only, show-only, max-issues, $GITHUB_STEP_SUMMARY append)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from aa_auto_sdr.core.exceptions import SnapshotError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.profiles import default_base
from aa_auto_sdr.output.diff_renderers._filters import filter_for_render
from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.models import DiffReport
from aa_auto_sdr.snapshot.resolver import resolve_snapshot

_VALID_FORMATS = ("console", "json", "markdown", "pr-comment")


def run(
    *,
    a: str,
    b: str,
    format_name: str | None,
    output: str | None,
    profile: str | None,
    side_by_side: bool = False,
    summary: bool = False,
    ignore_fields: frozenset[str] = frozenset(),
    quiet: bool = False,
    labels: tuple[str, str] | None = None,
    reverse: bool = False,
    changes_only: bool = False,
    show_only: frozenset[str] = frozenset(),
    max_issues: int | None = None,
    warn_threshold: int | None = None,
    color_theme: str = "default",
) -> int:
    from aa_auto_sdr.core import colors

    colors.set_theme(color_theme)
    fmt = format_name or "console"
    if fmt not in _VALID_FORMATS:
        print(
            f"error: format '{fmt}' is not available for --diff (use console|json|markdown|pr-comment)",
            flush=True,
        )
        return ExitCode.OUTPUT.value
    if fmt == "console" and output == "-":
        print(
            "error: --format console cannot pipe to stdout (use --format json|markdown for pipes)",
            flush=True,
        )
        return ExitCode.OUTPUT.value

    if reverse:
        a, b = b, a

    profile_snapshot_dir = default_base() / "orgs" / profile / "snapshots" if profile else None
    repo_root = Path.cwd()

    try:
        env_a = resolve_snapshot(
            a,
            profile_snapshot_dir=profile_snapshot_dir,
            repo_root=repo_root,
        )
        env_b = resolve_snapshot(
            b,
            profile_snapshot_dir=profile_snapshot_dir,
            repo_root=repo_root,
        )
    except SnapshotError as exc:
        if fmt in ("json", "markdown") and output == "-":
            from aa_auto_sdr.output.error_envelope import emit_error_envelope

            emit_error_envelope(exc, ExitCode.SNAPSHOT.value)
        else:
            print(f"snapshot error: {exc}", flush=True)
        return ExitCode.SNAPSHOT.value

    full_report = compare(env_a, env_b, ignore_fields=ignore_fields)
    # Compute warn-threshold against the FULL (unfiltered) report — per spec section 2.4.
    total_changes = sum(len(c.added) + len(c.removed) + len(c.modified) for c in full_report.components)

    # Apply presentational filters before render. The filters are pure copies;
    # full_report stays intact for warn-threshold and step-summary computation.
    report = filter_for_render(
        full_report,
        changes_only=changes_only,
        show_only=show_only,
        max_issues=max_issues,
    )

    if fmt == "console":
        rendered = render_console(
            report,
            side_by_side=side_by_side,
            summary=summary,
            quiet=quiet,
            labels=labels,
        )
    elif fmt == "json":
        rendered = render_json(report, summary=summary, labels=labels)
    elif fmt == "markdown":
        rendered = render_markdown(
            report,
            side_by_side=side_by_side,
            summary=summary,
            quiet=quiet,
            labels=labels,
        )
    else:  # pr-comment
        rendered = render_pr_comment(report, summary=summary, labels=labels)

    if output is None or output == "-":
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered)
        print(f"wrote: {target}", flush=True)

    # GitHub Actions: when GITHUB_STEP_SUMMARY is set, append a markdown view
    # using the FULL report (no presentational filters) so CI surfaces are
    # never misleadingly trimmed.
    _maybe_append_step_summary(full_report, labels=labels)

    if warn_threshold is not None and total_changes >= warn_threshold:
        return ExitCode.WARN.value
    return ExitCode.OK.value


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
