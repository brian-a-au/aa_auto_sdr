"""Snapshot envelope schema (v3).

Envelope shape (canonical, v3):
    {
        "schema": "aa-sdr-snapshot/v3",
        "rsid": "<RSID>",
        "captured_at": "<ISO-8601 with offset>",
        "tool_version": "<x.y.z>",
        "degraded_components": [<component-type>, ...],
        "partial_components": {<component-type>: <expansion_level>, ...},
        "quality": {<audit-name>: {...}, ...} | null,
        "components": { ... }
    }

`degraded_components` and `partial_components` are ALWAYS present in v2/v3
envelopes (empty list/dict when nothing is degraded). Component-type names
are the plural envelope-key form: "virtual_report_suites", "classifications".

`quality` (v3+) is null when no audit ran; populated by sdr/quality.py audits
(naming_audit, stale_components). Promoted to envelope top-level alongside
degraded_components / partial_components.

Reader-side, v1, v2, and v3 envelopes are accepted. v1 envelopes lack the
v2 keys; v1/v2 envelopes lack the v3 `quality` key. `validate_envelope`
defaults missing keys in-memory so all callers can bracket-index uniformly.

Header fields are promoted out of `SdrDocument.to_dict()`; everything else
goes under `components` (so future schema migrations only need to touch the
nested map)."""

from __future__ import annotations

import re
from typing import Any

from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument

SCHEMA_VERSION = "aa-sdr-snapshot/v3"
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
_SUPPORTED_SCHEMA_RE = re.compile(r"^aa-sdr-snapshot/v[123](\.\d+)?$")
# Match aware ISO 8601: must end with Z or [+|-]HH:MM offset.
_AWARE_TS_RE = re.compile(r".+(Z|[+-]\d{2}:\d{2})$")


def document_to_envelope(doc: SdrDocument) -> dict[str, Any]:
    """Build a v3 envelope from an SdrDocument.

    `degraded_components` and `partial_components` are always present;
    healthy snapshots carry empty list/dict respectively.
    `quality` is always present at top level (None when no audit ran).
    """
    payload = doc.to_dict()
    captured_at = payload.pop("captured_at")
    tool_version = payload.pop("tool_version")
    # quality + fetch_status are now produced by to_dict() (v1.12.0 fix).
    # The envelope hoists `quality` to the top level and partitions
    # fetch_status into degraded/partial keys, so pop them out of the
    # nested `components` payload to avoid duplication.
    quality = payload.pop("quality", None)
    payload.pop("fetch_status", None)
    degraded = sorted(ctype for ctype, meta in doc.fetch_status.items() if meta.status == "degraded")
    partial = {
        ctype: meta.expansion_level for ctype, meta in sorted(doc.fetch_status.items()) if meta.status == "partial"
    }
    return {
        "schema": SCHEMA_VERSION,
        "rsid": doc.report_suite.rsid,
        "captured_at": captured_at,
        "tool_version": tool_version,
        "degraded_components": degraded,
        "partial_components": partial,
        "quality": quality,  # NEW (v3)
        "components": payload,
    }


def validate_envelope(env: dict[str, Any]) -> None:
    """Raise SnapshotSchemaError if `env` is not a valid v1, v2, or v3 envelope.

    v1 envelopes do not require `degraded_components` / `partial_components`
    keys; this function defaults them in-memory (disk file unchanged) so every
    code path that goes through validation can uniformly bracket-index those
    keys. v2/v3 envelopes already have the keys (validated below).

    v1/v2 envelopes do not carry `quality`; defaulted to None in-memory so
    all readers see a uniform shape regardless of producer version.
    """
    if "schema" not in env:
        raise SnapshotSchemaError("snapshot envelope missing required key 'schema'")
    schema = env["schema"]
    if not isinstance(schema, str) or not _SUPPORTED_SCHEMA_RE.match(schema):
        raise SnapshotSchemaError(
            f"unsupported snapshot schema {schema!r}; expected 'aa-sdr-snapshot/v1', 'aa-sdr-snapshot/v2', or 'aa-sdr-snapshot/v3' (or vN.x minor bump)",
        )
    is_v3 = schema.startswith("aa-sdr-snapshot/v3")
    is_v2 = schema.startswith("aa-sdr-snapshot/v2")
    # v1 → v2/v3 forward-compat: default new keys for v1 envelopes (in-memory only).
    # v2/v3 envelopes already have these keys (validated below).
    if not is_v2 and not is_v3:
        env.setdefault("degraded_components", [])
        env.setdefault("partial_components", {})
    # v1/v2 envelopes don't carry `quality`; default to None in-memory so
    # all readers (comparator, writers) can index it uniformly.
    env.setdefault("quality", None)
    required = _REQUIRED_V2_KEYS if (is_v2 or is_v3) else _REQUIRED_V1_KEYS
    for key in required:
        if key not in env:
            raise SnapshotSchemaError(f"snapshot envelope missing required key '{key}'")
    captured_at = env["captured_at"]
    if not isinstance(captured_at, str) or not _AWARE_TS_RE.match(captured_at):
        raise SnapshotSchemaError(
            f"snapshot captured_at must be a timezone-aware ISO-8601 timestamp, got {captured_at!r}",
        )
    # Type-check fetch-status keys uniformly (covers v1-defaulted, v1-with-keys,
    # and v2). After the setdefault, both keys are guaranteed present.
    if not isinstance(env["degraded_components"], list):
        raise SnapshotSchemaError("degraded_components must be a list")
    if not isinstance(env["partial_components"], dict):
        raise SnapshotSchemaError("partial_components must be a dict")
