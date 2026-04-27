"""--list-snapshots and --prune-snapshots handlers."""

from __future__ import annotations

import json
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


def list_run(
    *,
    profile: str | None,
    rsid: str | None,
    format_name: str | None,
) -> int:
    """List snapshots in `~/.aa/orgs/<profile>/snapshots/`.

    Format: table (default) or json. `rsid` filters to one RSID."""
    if not profile:
        print("error: --list-snapshots requires --profile", flush=True)
        return ExitCode.CONFIG.value
    snapshot_dir = default_base() / "orgs" / profile / "snapshots"
    files = list_snapshots(snapshot_dir, rsid=rsid)
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
        return ExitCode.OUTPUT.value
    return ExitCode.OK.value


def prune_run(
    *,
    profile: str | None,
    rsid: str | None,
    keep_last: int | None,
    keep_since: str | None,
    dry_run: bool,
    assume_yes: bool = False,
) -> int:
    """Apply retention policy under `~/.aa/orgs/<profile>/snapshots/`.

    Requires `--profile` and at least one of `keep_last` / `keep_since`.
    `rsid` filters to one RSID. `dry_run` reports what would be deleted
    without unlinking. `assume_yes` skips the confirmation prompt for
    non-dry-run deletes (v1.2 destructive-action gate)."""
    if not profile:
        print("error: --prune-snapshots requires --profile", flush=True)
        return ExitCode.CONFIG.value
    try:
        policy = parse_policy(keep_last=keep_last, keep_since=keep_since)
    except ConfigError as exc:
        print(f"error: {exc}", flush=True)
        return ExitCode.CONFIG.value
    if not policy.is_active():
        print(
            "error: --prune-snapshots requires --keep-last or --keep-since",
            flush=True,
        )
        return ExitCode.CONFIG.value
    snapshot_dir = default_base() / "orgs" / profile / "snapshots"

    if not dry_run:
        from aa_auto_sdr.core._confirm import confirm

        # Probe with dry-run first so we can show the user how many files
        # would be deleted before they confirm.
        would_delete = prune_snapshots(snapshot_dir, policy, rsid=rsid, dry_run=True)
        if would_delete and not confirm(
            f"about to delete {len(would_delete)} snapshots; continue?",
            assume_yes=assume_yes,
        ):
            print(
                "aborted: non-interactive stdin detected; pass --yes to skip the confirmation",
                flush=True,
            )
            return ExitCode.USAGE.value

    deleted = prune_snapshots(snapshot_dir, policy, rsid=rsid, dry_run=dry_run)
    label = "would delete" if dry_run else "deleted"
    if not deleted:
        print(f"{label}: 0 snapshots")
    else:
        print(f"{label}: {len(deleted)} snapshots")
        for p in deleted:
            print(f"  {p}")
    return ExitCode.OK.value


def _to_row(path: Path) -> dict[str, str]:
    return {
        "rsid": path.parent.name,
        "captured_at": filename_to_captured_at(path.stem),
        "path": str(path),
    }
