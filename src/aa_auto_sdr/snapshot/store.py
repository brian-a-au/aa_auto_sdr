"""Snapshot save/load. Filesystem layer over snapshot/schema.py.

Path convention (called by CLI commands with the per-profile snapshot dir):
    <snapshot_dir>/<rsid>/<captured_at-fs-safe>.json

Filenames replace ISO-8601 colons with hyphens for cross-FS safety. The
in-payload `captured_at` field keeps the proper colon form."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aa_auto_sdr.core.exceptions import OutputError
from aa_auto_sdr.core.json_io import read_json, write_json
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot.schema import document_to_envelope, validate_envelope


def captured_at_to_filename(captured_at_iso: str) -> str:
    """Make an ISO-8601 timestamp filesystem-safe by colon→hyphen substitution.

    `2026-04-26T17:29:01+00:00` → `2026-04-26T17-29-01+00-00.json`."""
    return captured_at_iso.replace(":", "-") + ".json"


def snapshot_path(*, snapshot_dir: Path, rsid: str, captured_at_iso: str) -> Path:
    """Return the canonical snapshot path under `<snapshot_dir>/<rsid>/<filename>`."""
    return snapshot_dir / rsid / captured_at_to_filename(captured_at_iso)


def save_snapshot(doc: SdrDocument, *, snapshot_dir: Path) -> Path:
    """Build envelope and atomic-write under the canonical path. Returns the file path.

    Filesystem errors are wrapped in OutputError so run_batch can fold the
    failure into BatchFailure (per v0.7 spec §3) instead of aborting the run."""
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
    return target


def load_snapshot(path: Path) -> dict[str, Any]:
    """Load and validate a snapshot envelope. Raises SnapshotSchemaError on bad shape."""
    payload = read_json(path)
    validate_envelope(payload)
    return payload
