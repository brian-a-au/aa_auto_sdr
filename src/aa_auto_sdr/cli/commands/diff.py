"""diff command — wire side-by-side, summary, ignore-fields, pr-comment."""

from __future__ import annotations

import sys
from pathlib import Path

from aa_auto_sdr.core.exceptions import SnapshotError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.profiles import default_base
from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.comparator import compare
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
) -> int:
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

    report = compare(env_a, env_b, ignore_fields=ignore_fields)

    if fmt == "console":
        rendered = render_console(report, side_by_side=side_by_side, summary=summary)
    elif fmt == "json":
        rendered = render_json(report, summary=summary)
    elif fmt == "markdown":
        rendered = render_markdown(report, side_by_side=side_by_side, summary=summary)
    else:  # pr-comment
        rendered = render_pr_comment(report, summary=summary)

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

    return ExitCode.OK.value
