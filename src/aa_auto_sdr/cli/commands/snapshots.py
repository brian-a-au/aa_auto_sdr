"""--list-snapshots and --prune-snapshots handlers."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.profiles import default_base
from aa_auto_sdr.snapshot.retention import parse_policy
from aa_auto_sdr.snapshot.store import (
    filename_to_captured_at,
    list_snapshots,
    prune_snapshots,
)

logger = logging.getLogger(__name__)


def list_run(
    *,
    profile: str | None,
    rsid: str | None,
    format_name: str | None,
    snapshot_dir: Path | None = None,
) -> int:
    """List snapshots in the active snapshot directory.

    Resolves: --snapshot-dir > ~/.aa/orgs/<profile>/snapshots.
    Requires at least one of --profile or --snapshot-dir.
    Format: table (default) or json. `rsid` filters to one RSID."""
    started_ms = time.monotonic()
    logger.info("command_start command=list_snapshots", extra={"command": "list_snapshots"})
    exit_code = ExitCode.GENERIC.value
    try:
        if not profile and not snapshot_dir:
            print(
                "error: --list-snapshots requires --profile or --snapshot-dir",
                flush=True,
            )
            exit_code = ExitCode.CONFIG.value
            return exit_code
        snap_dir = snapshot_dir or default_base() / "orgs" / profile / "snapshots"
        files = list_snapshots(snap_dir, rsid=rsid)
        fmt = format_name or "table"
        if fmt == "json":
            rows = [_to_row(p) for p in files]
            print(json.dumps(rows, sort_keys=True, indent=2))
        elif fmt == "table":
            if not files:
                print("(no snapshots)")
            else:
                print(f"{'RSID':<20}  {'CAPTURED_AT':<32}  PATH")
                for p in files:
                    row = _to_row(p)
                    print(f"{row['rsid']:<20}  {row['captured_at']:<32}  {row['path']}")
        else:
            print(
                f"error: --list-snapshots format must be json|table (got '{fmt}')",
                flush=True,
            )
            exit_code = ExitCode.OUTPUT.value
            return exit_code
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=list_snapshots exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "list_snapshots",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def prune_run(
    *,
    profile: str | None,
    rsid: str | None,
    keep_last: int | None,
    keep_since: str | None,
    dry_run: bool,
    assume_yes: bool = False,
    snapshot_dir: Path | None = None,
) -> int:
    """Apply retention policy under the active snapshot directory.

    Resolves: --snapshot-dir > ~/.aa/orgs/<profile>/snapshots.
    Requires at least one of --profile or --snapshot-dir, plus a policy flag
    (`keep_last` / `keep_since`). `rsid` filters to one RSID. `dry_run` reports
    what would be deleted without unlinking. `assume_yes` skips the
    confirmation prompt for non-dry-run deletes."""
    started_ms = time.monotonic()
    logger.info("command_start command=prune_snapshots", extra={"command": "prune_snapshots"})
    exit_code = ExitCode.GENERIC.value
    try:
        if not profile and not snapshot_dir:
            print(
                "error: --prune-snapshots requires --profile or --snapshot-dir",
                flush=True,
            )
            exit_code = ExitCode.CONFIG.value
            return exit_code
        try:
            policy = parse_policy(keep_last=keep_last, keep_since=keep_since)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        if not policy.is_active():
            print(
                "error: --prune-snapshots requires --keep-last or --keep-since",
                flush=True,
            )
            exit_code = ExitCode.CONFIG.value
            return exit_code
        snap_dir = snapshot_dir or default_base() / "orgs" / profile / "snapshots"

        if not dry_run:
            from aa_auto_sdr.core._confirm import confirm

            # Probe with dry-run first so we can show the user how many files
            # would be deleted before they confirm.
            would_delete = prune_snapshots(snap_dir, policy, rsid=rsid, dry_run=True)
            if would_delete and not confirm(
                f"about to delete {len(would_delete)} snapshots; continue?",
                assume_yes=assume_yes,
            ):
                print(
                    "aborted: non-interactive stdin detected; pass --yes to skip the confirmation",
                    flush=True,
                )
                exit_code = ExitCode.USAGE.value
                return exit_code

        deleted = prune_snapshots(snap_dir, policy, rsid=rsid, dry_run=dry_run)
        label = "would delete" if dry_run else "deleted"
        if not deleted:
            print(f"{label}: 0 snapshots")
        else:
            print(f"{label}: {len(deleted)} snapshots")
            for p in deleted:
                print(f"  {p}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=prune_snapshots exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "prune_snapshots",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _to_row(path: Path) -> dict[str, str]:
    return {
        "rsid": path.parent.name,
        "captured_at": filename_to_captured_at(path.stem),
        "path": str(path),
    }
