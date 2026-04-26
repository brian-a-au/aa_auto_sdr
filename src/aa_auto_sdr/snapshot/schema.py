"""Snapshot envelope schema (v1).

Envelope shape (canonical):
    {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "<RSID>",
        "captured_at": "<ISO-8601 with offset>",
        "tool_version": "<x.y.z>",
        "components": { ... }
    }

Header fields are promoted out of `SdrDocument.to_dict()`; everything else
goes under `components` (so future schema migrations only need to touch the
nested map)."""

from __future__ import annotations

import re
from typing import Any

from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument

SCHEMA_VERSION = "aa-sdr-snapshot/v1"
_REQUIRED_KEYS = ("schema", "rsid", "captured_at", "tool_version", "components")
_SCHEMA_PREFIX = "aa-sdr-snapshot/v1"
# Match aware ISO 8601: must end with Z or [+|-]HH:MM offset.
_AWARE_TS_RE = re.compile(r".+(Z|[+-]\d{2}:\d{2})$")


def document_to_envelope(doc: SdrDocument) -> dict[str, Any]:
    """Build a v1 envelope from an SdrDocument."""
    payload = doc.to_dict()
    captured_at = payload.pop("captured_at")
    tool_version = payload.pop("tool_version")
    return {
        "schema": SCHEMA_VERSION,
        "rsid": doc.report_suite.rsid,
        "captured_at": captured_at,
        "tool_version": tool_version,
        "components": payload,
    }


def validate_envelope(env: dict[str, Any]) -> None:
    """Raise SnapshotSchemaError if `env` is not a valid v1 envelope."""
    for key in _REQUIRED_KEYS:
        if key not in env:
            raise SnapshotSchemaError(f"snapshot envelope missing required key '{key}'")
    schema = env["schema"]
    if not isinstance(schema, str) or not schema.startswith(_SCHEMA_PREFIX):
        raise SnapshotSchemaError(
            f"unsupported snapshot schema {schema!r}; expected '{_SCHEMA_PREFIX}' (or v1.x minor bump)",
        )
    captured_at = env["captured_at"]
    if not isinstance(captured_at, str) or not _AWARE_TS_RE.match(captured_at):
        raise SnapshotSchemaError(
            f"snapshot captured_at must be a timezone-aware ISO-8601 timestamp, got {captured_at!r}",
        )
