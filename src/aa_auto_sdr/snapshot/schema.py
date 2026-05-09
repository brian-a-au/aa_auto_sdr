"""Snapshot envelope schema (v2).

Envelope shape (canonical, v2):
    {
        "schema": "aa-sdr-snapshot/v2",
        "rsid": "<RSID>",
        "captured_at": "<ISO-8601 with offset>",
        "tool_version": "<x.y.z>",
        "degraded_components": [<component-type>, ...],
        "partial_components": {<component-type>: <expansion_level>, ...},
        "components": { ... }
    }

`degraded_components` and `partial_components` are ALWAYS present in v2
envelopes (empty list/dict when nothing is degraded). Component-type names
are the plural envelope-key form: "virtual_report_suites", "classifications".

Reader-side, both v1 and v2 envelopes are accepted. v1 envelopes lack the
new keys; the loader (`store.load_snapshot`) defaults them to `[]`/`{}`.

Header fields are promoted out of `SdrDocument.to_dict()`; everything else
goes under `components` (so future schema migrations only need to touch the
nested map)."""

from __future__ import annotations

import re
from typing import Any

from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument

SCHEMA_VERSION = "aa-sdr-snapshot/v2"
_REQUIRED_V2_KEYS = (
    "schema",
    "rsid",
    "captured_at",
    "tool_version",
    "degraded_components",
    "partial_components",
    "components",
)
_REQUIRED_V1_KEYS = (
    "schema",
    "rsid",
    "captured_at",
    "tool_version",
    "components",
)
_SUPPORTED_SCHEMA_RE = re.compile(r"^aa-sdr-snapshot/v[12](\.\d+)?$")
# Match aware ISO 8601: must end with Z or [+|-]HH:MM offset.
_AWARE_TS_RE = re.compile(r".+(Z|[+-]\d{2}:\d{2})$")


def document_to_envelope(doc: SdrDocument) -> dict[str, Any]:
    """Build a v2 envelope from an SdrDocument.

    `degraded_components` and `partial_components` are always present;
    healthy snapshots carry empty list/dict respectively.
    """
    payload = doc.to_dict()
    captured_at = payload.pop("captured_at")
    tool_version = payload.pop("tool_version")
    fetch_status = payload.pop("fetch_status", {})
    degraded = sorted(ctype for ctype, meta in fetch_status.items() if meta["status"] == "degraded")
    partial = {
        ctype: meta["expansion_level"] for ctype, meta in sorted(fetch_status.items()) if meta["status"] == "partial"
    }
    return {
        "schema": SCHEMA_VERSION,
        "rsid": doc.report_suite.rsid,
        "captured_at": captured_at,
        "tool_version": tool_version,
        "degraded_components": degraded,
        "partial_components": partial,
        "components": payload,
    }


def validate_envelope(env: dict[str, Any]) -> None:
    """Raise SnapshotSchemaError if `env` is not a valid v1 or v2 envelope.

    v1 envelopes do not require `degraded_components` / `partial_components`
    keys (the loader defaults them after validation). v2 envelopes require
    both keys to be present.
    """
    schema = env.get("schema")
    if not isinstance(schema, str) or not _SUPPORTED_SCHEMA_RE.match(schema):
        raise SnapshotSchemaError(
            f"unsupported snapshot schema {schema!r}; expected 'aa-sdr-snapshot/v1' or 'aa-sdr-snapshot/v2' (or v1.x / v2.x minor bump)",
        )
    is_v2 = schema.startswith("aa-sdr-snapshot/v2")
    required = _REQUIRED_V2_KEYS if is_v2 else _REQUIRED_V1_KEYS
    for key in required:
        if key not in env:
            raise SnapshotSchemaError(f"snapshot envelope missing required key '{key}'")
    captured_at = env["captured_at"]
    if not isinstance(captured_at, str) or not _AWARE_TS_RE.match(captured_at):
        raise SnapshotSchemaError(
            f"snapshot captured_at must be a timezone-aware ISO-8601 timestamp, got {captured_at!r}",
        )
    if is_v2:
        if not isinstance(env["degraded_components"], list):
            raise SnapshotSchemaError("degraded_components must be a list")
        if not isinstance(env["partial_components"], dict):
            raise SnapshotSchemaError("partial_components must be a dict")
