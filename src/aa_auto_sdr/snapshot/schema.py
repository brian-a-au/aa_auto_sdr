"""Snapshot envelope schema (v4).

Envelope shape (canonical, v4):
    {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "<RSID>",
        "captured_at": "<ISO-8601 with offset>",
        "tool_version": "<x.y.z>",
        "degraded_components": [<component-type>, ...],
        "partial_components": {<component-type>: <expansion_level>, ...},
        "quality": {
            "naming_audit": {...},
            "stale_components": [...],
            "issues": [...],   # v4 — added in v1.12.0
            "summary": {...},  # v4 — added in v1.12.0
        } | null,
        "components": { ... }
    }

`degraded_components` and `partial_components` are ALWAYS present in v2-v4
envelopes (empty list/dict when nothing is degraded).

`quality` (v3+) is null when no audit ran. v4 (v1.12.0) adds two additive
keys inside the quality block: `issues` (severity-tagged findings) and
`summary` (counts + verdict). v3 envelopes still load on v1.12.0 — missing
v4 keys are defaulted in-memory.

Reader-side, v1-v4 envelopes are accepted. Forward-compat in-memory
defaults keep all callers indexing uniformly.

Header fields are promoted out of `SdrDocument.to_dict()`; everything else
goes under `components` (so future schema migrations only need to touch the
nested map)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from aa_auto_sdr.core.exceptions import SnapshotCorruptError, SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument

SCHEMA_VERSION = "aa-sdr-snapshot/v4"
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
_SUPPORTED_SCHEMA_RE = re.compile(r"^aa-sdr-snapshot/v[1234](\.\d+)?$")


def _is_aware_iso_timestamp(value: str) -> bool:
    """True iff `value` parses as ISO 8601 AND carries a timezone offset.

    A suffix check alone (`...Z` / `...+HH:MM`) is not enough: a value like
    `garbage+00:00` would pass and then crash trending's fromisoformat later."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def document_to_envelope(doc: SdrDocument, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a v4 envelope from an SdrDocument.

    `degraded_components` and `partial_components` are always present;
    healthy snapshots carry empty list/dict respectively.
    `quality` is always present at top level (None when no audit ran).

    `payload`, when provided, is a pre-built `doc.to_dict()` result reused to
    avoid re-serializing the document. Callers that already have the dict pass
    it; otherwise it is computed here. `dict(payload)` shallow-copies so the
    `.pop()` calls below don't mutate the caller's dict (which the pipe path
    still emits to stdout).
    """
    payload = dict(payload) if payload is not None else doc.to_dict()
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
    """Raise SnapshotSchemaError if `env` is not a valid v1-v4 envelope.

    v1 envelopes do not require `degraded_components` / `partial_components`
    keys; this function defaults them in-memory (disk file unchanged) so every
    code path that goes through validation can uniformly bracket-index those
    keys. v2-v4 envelopes already have the keys (validated below).

    v1/v2 envelopes do not carry `quality`; defaulted to None in-memory so
    all readers see a uniform shape regardless of producer version.

    v3 envelopes carry `quality` but not the v4 inner `issues` + `summary`
    keys; defaulted in-memory so consumers can index them uniformly.
    """
    # Classify the discriminator before inspecting supported-version contents.
    # Unsupported string schemas must never be mistaken for recoverable damage.
    if not isinstance(env, dict):
        raise SnapshotCorruptError("snapshot envelope must be a dict")
    if "schema" not in env:
        raise SnapshotCorruptError("snapshot envelope missing required key 'schema'")
    schema = env["schema"]
    if not isinstance(schema, str):
        raise SnapshotCorruptError("snapshot schema must be a string")
    if not _SUPPORTED_SCHEMA_RE.match(schema):
        raise SnapshotSchemaError(
            f"unsupported snapshot schema {schema!r}; expected "
            f"'aa-sdr-snapshot/v1'..'aa-sdr-snapshot/v4' (or vN.x minor bump)",
        )
    is_v1 = schema.startswith("aa-sdr-snapshot/v1")
    required = _REQUIRED_V1_KEYS if is_v1 else _REQUIRED_V2_KEYS
    for key in required:
        if key not in env:
            raise SnapshotCorruptError(f"snapshot envelope missing required key '{key}'")
    captured_at = env["captured_at"]
    if not isinstance(captured_at, str) or not _is_aware_iso_timestamp(captured_at):
        raise SnapshotCorruptError(
            f"snapshot captured_at must be a timezone-aware ISO-8601 timestamp, got {captured_at!r}",
        )

    # Validate all consumed containers before applying compatibility defaults.
    # Missing optional sections remain supported; row identity is checked only
    # at the watch comparison boundary, not by this shared reader.
    _require_container(env["components"], dict, "components")
    components = env["components"]
    if "report_suite" in components:
        _require_container(components["report_suite"], dict, "components.report_suite")
    for section in (
        "dimensions",
        "metrics",
        "segments",
        "calculated_metrics",
        "virtual_report_suites",
        "classifications",
    ):
        if section in components:
            _require_mapping_rows(components[section], f"components.{section}")
    if "degraded_components" in env:
        _require_container(env["degraded_components"], list, "degraded_components")
    if "partial_components" in env:
        _require_container(env["partial_components"], dict, "partial_components")
    quality = env.get("quality")
    if quality is not None:
        _require_container(quality, dict, "quality")
        if "naming_audit" in quality:
            _require_container(quality["naming_audit"], dict, "quality.naming_audit")
        for section in ("stale_components", "issues"):
            if section in quality:
                _require_mapping_rows(quality[section], f"quality.{section}")
        if "summary" in quality:
            _require_container(quality["summary"], dict, "quality.summary")
            if "by_severity" in quality["summary"]:
                _require_container(quality["summary"]["by_severity"], dict, "quality.summary.by_severity")

    if is_v1:
        env.setdefault("degraded_components", [])
        env.setdefault("partial_components", {})
    env.setdefault("quality", None)
    if quality is not None:
        quality.setdefault("issues", [])
        quality.setdefault("summary", {"by_severity": {}, "total": 0, "verdict": "n/a"})


def _require_container(value: Any, kind: type, field: str) -> None:
    if not isinstance(value, kind):
        raise SnapshotCorruptError(f"{field} must be a {kind.__name__}")


def _require_mapping_rows(value: Any, field: str) -> None:
    _require_container(value, list, field)
    if any(not isinstance(row, dict) for row in value):
        raise SnapshotCorruptError(f"{field} rows must be dicts")
