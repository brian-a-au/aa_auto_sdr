"""--compare-with-prev: sugar over `--diff <RSID>@previous <RSID>@latest`.

Multi-RSID support: loops over each RSID, dispatches one diff per RSID,
returns the *highest* exit code seen. The plausible exit codes from
`--diff` are OK (0), CONFIG (10), AUTH (11), API (12), NOT_FOUND (13),
OUTPUT (15), SNAPSHOT (16) — all non-zero error states, so integer max
approximates "worst" well enough for this command's needs. WARN (3) is
not produced by this path. If a future diff path returns WARN, the
ranking stays sane (WARN < CONFIG by integer value, so a single CONFIG
still wins).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from aa_auto_sdr.cli.commands import diff as diff_cmd
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
    """Run --diff for each RSID with synthesized @previous/@latest tokens."""
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
            )
            exit_code = ExitCode.USAGE.value
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
            )
            worst = max(worst, rc)
        exit_code = worst
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
