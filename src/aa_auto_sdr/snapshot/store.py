"""Snapshot save/load + list/prune. Filesystem layer over snapshot/schema.py.

Path convention (called by CLI commands with the per-profile snapshot dir):
    <snapshot_dir>/<rsid>/<captured_at-fs-safe>.json

Filenames replace ISO-8601 colons with hyphens for cross-FS safety. The
in-payload `captured_at` field keeps the proper colon form."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aa_auto_sdr.core.exceptions import OutputError
from aa_auto_sdr.core.json_io import read_json, write_json
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot.schema import document_to_envelope, validate_envelope

if TYPE_CHECKING:
    from aa_auto_sdr.snapshot.retention import RetentionPolicy

logger = logging.getLogger(__name__)


def captured_at_to_filename(captured_at_iso: str) -> str:
    """Make an ISO-8601 timestamp filesystem-safe by colon→hyphen substitution.

    `2026-04-26T17:29:01+00:00` → `2026-04-26T17-29-01+00-00.json`."""
    return captured_at_iso.replace(":", "-") + ".json"


def filename_to_captured_at(filename_stem: str) -> str:
    """Inverse of captured_at_to_filename. Restore colons in the time portion.

    `2026-04-26T17-29-01+00-00` → `2026-04-26T17:29:01+00:00`.

    Tolerates the `Z` UTC suffix variant accepted by snapshot.schema."""
    if "T" not in filename_stem:
        return filename_stem  # not a recognized timestamp shape; pass through
    date, time_with_offset = filename_stem.split("T", 1)
    if time_with_offset.endswith("Z"):
        # 17-29-01Z → 17:29:01Z
        body = time_with_offset[:-1].replace("-", ":")
        return f"{date}T{body}Z"
    # The offset is always the trailing 6 chars in the form `[+-]HH-MM`
    # (since `captured_at_to_filename` only swaps colons → hyphens, the sign
    # is preserved). For `+`, rfind is unambiguous; for `-`, we anchor at the
    # length-6 position so the sign doesn't collide with HH-MM-SS hyphens.
    if len(time_with_offset) >= 6 and time_with_offset[-6] in "+-":
        sign_idx = len(time_with_offset) - 6
        time_part = time_with_offset[:sign_idx].replace("-", ":")
        offset_part = time_with_offset[sign_idx]  # the sign
        offset_body = time_with_offset[sign_idx + 1 :].replace("-", ":")
        return f"{date}T{time_part}{offset_part}{offset_body}"
    # No recognizable offset signal; convert all hyphens (best effort).
    return f"{date}T{time_with_offset.replace('-', ':')}"


def snapshot_path(*, snapshot_dir: Path, rsid: str, captured_at_iso: str) -> Path:
    """Return the canonical snapshot path under `<snapshot_dir>/<rsid>/<filename>`."""
    return snapshot_dir / rsid / captured_at_to_filename(captured_at_iso)


def save_snapshot(doc: SdrDocument, *, snapshot_dir: Path) -> Path:
    """Build envelope and atomic-write under the canonical path. Returns the file path.

    Filesystem errors are wrapped in OutputError so run_batch can fold the
    failure into BatchFailure (per v0.7 spec §3) instead of aborting the run."""
    started = time.monotonic()
    envelope = document_to_envelope(doc)
    target = snapshot_path(
        snapshot_dir=snapshot_dir,
        rsid=doc.report_suite.rsid,
        captured_at_iso=envelope["captured_at"],
    )
    try:
        write_json(target, envelope)
    except OSError as exc:
        raise OutputError(f"snapshot write failed at {target}: {exc}") from exc
    duration_ms = int((time.monotonic() - started) * 1000)
    component_count = (
        len(doc.dimensions)
        + len(doc.metrics)
        + len(doc.segments)
        + len(doc.calculated_metrics)
        + len(doc.virtual_report_suites)
        + len(doc.classifications)
    )
    logger.info(
        "snapshot_save snapshot_id=%s rsid=%s output_path=%s count=%s duration_ms=%s",
        target.stem,
        doc.report_suite.rsid,
        str(target),
        component_count,
        duration_ms,
        extra={
            "snapshot_id": target.stem,
            "rsid": doc.report_suite.rsid,
            "output_path": str(target),
            "count": component_count,
            "duration_ms": duration_ms,
        },
    )
    return target


def load_snapshot(path: Path) -> dict[str, Any]:
    """Load and validate a snapshot envelope. Raises SnapshotSchemaError on bad shape."""
    payload = read_json(path)
    validate_envelope(payload)
    # Component count for triage; cheap lookup from envelope shape (see
    # snapshot/schema.py — components live under the `components` key).
    components = payload.get("components", {})
    count = sum(
        len(components.get(k, []))
        for k in (
            "dimensions",
            "metrics",
            "segments",
            "calculated_metrics",
            "virtual_report_suites",
            "classifications",
        )
    )
    logger.debug(
        "snapshot loaded snapshot_id=%s count=%s",
        path.stem,
        count,
        extra={"snapshot_id": path.stem, "count": count},
    )
    return payload


def list_snapshots(snapshot_dir: Path, *, rsid: str | None = None) -> list[Path]:
    """List snapshot files under `snapshot_dir`, optionally filtered to one RSID.

    Returns paths sorted chronologically (oldest first). Returns [] if the
    directory doesn't exist or has no matching snapshots."""
    if rsid is not None:
        rs_dir = snapshot_dir / rsid
        if not rs_dir.exists():
            logger.debug(
                "list_snapshots rsid=%s count=0 (dir missing)",
                rsid,
                extra={"count": 0, "rsid": rsid},
            )
            return []
        files = sorted(rs_dir.glob("*.json"))
        logger.debug(
            "list_snapshots rsid=%s count=%s",
            rsid,
            len(files),
            extra={"count": len(files), "rsid": rsid},
        )
        return files
    if not snapshot_dir.exists():
        logger.debug(
            "list_snapshots cross-rsid count=0 (dir missing)",
            extra={"count": 0},
        )
        return []
    files = sorted(p for rs in snapshot_dir.iterdir() if rs.is_dir() for p in rs.glob("*.json"))
    logger.debug(
        "list_snapshots cross-rsid count=%s",
        len(files),
        extra={"count": len(files)},
    )
    return files


def prune_snapshots(
    snapshot_dir: Path,
    policy: RetentionPolicy,
    *,
    rsid: str | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> list[Path]:
    """Apply `policy` to each RSID under `snapshot_dir` (or one RSID).

    Returns paths actually deleted (or that would be, if dry_run). Pruning is
    per-RSID — `--keep-last 5` keeps 5 *per RSID*, not 5 total.

    Per-file unlink failures are logged at WARNING and skipped — a single
    corrupt or locked file does not abort a multi-RSID prune."""
    from aa_auto_sdr.snapshot.retention import select_for_deletion  # local import

    rsids = [rsid] if rsid else _list_rsids(snapshot_dir)
    deleted: list[Path] = []
    for r in rsids:
        files = list_snapshots(snapshot_dir, rsid=r)
        for f in select_for_deletion(files, policy, now=now):
            if not dry_run:
                try:
                    f.unlink()
                except OSError as exc:
                    logger.warning(
                        "prune skipped output_path=%s error_class=%s",
                        str(f),
                        type(exc).__name__,
                        extra={
                            "output_path": str(f),
                            "error_class": type(exc).__name__,
                        },
                    )
                    continue
            deleted.append(f)
    if deleted:
        logger.info(
            "prune_snapshots removed count=%s rsid=%s",
            len(deleted),
            rsid or "all",
            extra={"count": len(deleted), "rsid": rsid or "all"},
        )
    return sorted(deleted)


def _list_rsids(snapshot_dir: Path) -> list[str]:
    """List RSID subdirectories under `snapshot_dir`. Returns [] if missing."""
    if not snapshot_dir.exists():
        return []
    return sorted(p.name for p in snapshot_dir.iterdir() if p.is_dir())
