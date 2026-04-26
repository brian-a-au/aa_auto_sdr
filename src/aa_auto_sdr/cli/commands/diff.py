"""diff command: resolve two tokens → compare → render → write to --output.

Owns all I/O. The pure pieces (resolver, comparator, renderers) are tested
without capsys/tmp_path. See v0.7 spec sections 4-6 + 8.

Exit codes:
  0   diff succeeded (regardless of whether deltas exist)
  10  ConfigError (missing profile / token requires profile)
  15  bad --format or --output combination
  16  SnapshotError (resolve / schema / git failure)
"""

from __future__ import annotations

import sys
from pathlib import Path

from aa_auto_sdr.core.exceptions import SnapshotError
from aa_auto_sdr.core.profiles import default_base
from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.resolver import resolve_snapshot

_EXIT_OK = 0
_EXIT_OUTPUT = 15
_EXIT_SNAPSHOT = 16

_VALID_FORMATS = ("console", "json", "markdown")


def run(
    *,
    a: str,
    b: str,
    format_name: str | None,
    output: str | None,
    profile: str | None,
) -> int:
    fmt = format_name or "console"
    if fmt not in _VALID_FORMATS:
        print(
            f"error: format '{fmt}' is not available for --diff (use console|json|markdown)",
            flush=True,
        )
        return _EXIT_OUTPUT
    if fmt == "console" and output == "-":
        print(
            "error: --format console cannot pipe to stdout (use --format json|markdown for pipes)",
            flush=True,
        )
        return _EXIT_OUTPUT

    profile_snapshot_dir = (default_base() / "orgs" / profile / "snapshots") if profile else None
    repo_root = Path.cwd()

    try:
        env_a = resolve_snapshot(a, profile_snapshot_dir=profile_snapshot_dir, repo_root=repo_root)
        env_b = resolve_snapshot(b, profile_snapshot_dir=profile_snapshot_dir, repo_root=repo_root)
    except SnapshotError as exc:
        print(f"snapshot error: {exc}", flush=True)
        return _EXIT_SNAPSHOT

    report = compare(env_a, env_b)

    if fmt == "console":
        rendered = render_console(report)
    elif fmt == "json":
        rendered = render_json(report)
    else:
        rendered = render_markdown(report)

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

    return _EXIT_OK
