"""Snapshot diff algorithm — pure, takes two envelope dicts, returns a DiffReport.

Adopts two patterns from cja_auto_sdr/diff/comparator.py (audited 2026-04-26):
  * generic ID-keyed loop with parameterized field-allowlist
  * value normalization (whitespace strip, NaN/None/'' equivalence,
    order-insensitive 'tags'/'categories')

See v0.7 design spec §5 + §5.1 for design rationale."""

from __future__ import annotations

import dataclasses
import logging
import math
import time
from typing import Any

from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)

logger = logging.getLogger(__name__)

# Component types in canonical render order.
_COMPONENT_TYPES = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
)

# §5.1 — list fields whose semantic content is set-like (sort before compare).
ORDER_INSENSITIVE_LIST_FIELDS = {"tags", "categories"}

# v1.9.0 — fields suppressed from diff output by default. Pass
# extended_fields=True (CLI: --extended-fields) to include them.
# Grounded in api/models.py field names (Dimension, Metric, Segment, etc.).
_EXTENDED_FIELDS_DEFAULT_IGNORE: frozenset[str] = frozenset(
    {
        "description",
        "tags",
        "category",
        "data_group",
        "extra",
        "compatibility",
        "categories",
        "owner_id",
        "created",
        "modified",
    },
)


def compare(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    ignore_fields: frozenset[str] = frozenset(),
    extended_fields: bool = False,  # NEW (v1.9.0)
) -> DiffReport:
    """Diff two snapshot envelopes (assumed schema-validated by the caller).

    `ignore_fields` is a set of field names to skip during compare. The match is
    exact at every nesting level — `description` skips both top-level and nested
    `description` fields.

    `extended_fields` (v1.9.0+): when False (default), a default suppression
    set of noisy fields (description, tags, category, etc.) is added to
    `ignore_fields`. When True, only `ignore_fields` is applied — extended
    fields show up in the diff.
    """
    started = time.monotonic()
    a_components = a["components"]
    b_components = b["components"]

    effective_ignore = ignore_fields if extended_fields else (ignore_fields | _EXTENDED_FIELDS_DEFAULT_IGNORE)

    rs_deltas = _diff_dict(
        a_components["report_suite"],
        b_components["report_suite"],
        parent_field="",
        ignore_fields=effective_ignore,
    )

    components: list[ComponentDiff] = []
    for ctype in _COMPONENT_TYPES:
        cd = _diff_component_list(
            ctype,
            a_components.get(ctype, []),
            b_components.get(ctype, []),
            ignore_fields=effective_ignore,
        )
        suppressed, reason = _suppression_for(ctype, a, b)
        if suppressed:
            cd = dataclasses.replace(cd, suppressed=True, suppression_reason=reason)
        components.append(cd)

    report = DiffReport(
        a_rsid=a["rsid"],
        b_rsid=b["rsid"],
        a_captured_at=a["captured_at"],
        b_captured_at=b["captured_at"],
        a_tool_version=a["tool_version"],
        b_tool_version=b["tool_version"],
        report_suite_deltas=rs_deltas,
        components=components,
        rsid_mismatch=a["rsid"] != b["rsid"],
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    total_changes = sum(len(c.added) + len(c.removed) + len(c.modified) for c in report.components)
    rsid = a.get("rsid") or b.get("rsid") or ""
    logger.debug(
        "compare done rsid=%s count=%s duration_ms=%s",
        rsid,
        total_changes,
        duration_ms,
        extra={
            "rsid": rsid,
            "count": total_changes,
            "duration_ms": duration_ms,
        },
    )
    return report


def _diff_component_list(
    component_type: str,
    a_list: list[dict[str, Any]],
    b_list: list[dict[str, Any]],
    *,
    ignore_fields: frozenset[str] = frozenset(),
) -> ComponentDiff:
    a_by_id = {item["id"]: item for item in a_list}
    b_by_id = {item["id"]: item for item in b_list}

    added_ids = sorted(b_by_id.keys() - a_by_id.keys())
    removed_ids = sorted(a_by_id.keys() - b_by_id.keys())
    common_ids = sorted(a_by_id.keys() & b_by_id.keys())

    added = [AddedRemovedItem(id=i, name=str(b_by_id[i].get("name", i))) for i in added_ids]
    removed = [AddedRemovedItem(id=i, name=str(a_by_id[i].get("name", i))) for i in removed_ids]

    modified: list[ModifiedItem] = []
    unchanged = 0
    for cid in common_ids:
        deltas = _diff_dict(
            a_by_id[cid],
            b_by_id[cid],
            parent_field="",
            ignore_fields=ignore_fields,
        )
        if deltas:
            modified.append(
                ModifiedItem(
                    id=cid,
                    name=str(b_by_id[cid].get("name", cid)),
                    deltas=deltas,
                ),
            )
        else:
            unchanged += 1

    return ComponentDiff(
        component_type=component_type,
        added=added,
        removed=removed,
        modified=modified,
        unchanged_count=unchanged,
    )


def _suppression_for(
    component_type: str,
    a: dict[str, Any],
    b: dict[str, Any],
) -> tuple[bool, str | None]:
    """Apply spec §4.7 suppression rules. Returns (suppressed, reason)."""
    left_degraded = component_type in a.get("degraded_components", [])
    right_degraded = component_type in b.get("degraded_components", [])
    if left_degraded or right_degraded:
        return True, "fetch degraded"
    left_level = a.get("partial_components", {}).get(component_type)
    right_level = b.get("partial_components", {}).get(component_type)
    if left_level is None and right_level is None:
        return False, None
    if left_level == right_level:
        # both partial at the same level — comparable, fall through to normal diff
        return False, None
    level = left_level or right_level
    return True, f"fetch partial (expansion_level={level})"


def _diff_dict(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    parent_field: str,
    ignore_fields: frozenset[str] = frozenset(),
) -> list[FieldDelta]:
    """Walk two dicts and emit FieldDelta for each leaf inequality, after normalization.

    `id` and `rsid` are identity fields; mismatches surface via the parent
    DiffReport's added/removed lists or `rsid_mismatch` flag, so we skip them
    here to avoid emitting redundant deltas."""
    deltas: list[FieldDelta] = []
    keys = sorted(a.keys() | b.keys())
    for key in keys:
        if key in ("id", "rsid"):
            continue
        if key in ignore_fields:
            continue
        path = f"{parent_field}.{key}" if parent_field else key
        a_val = a.get(key)
        b_val = b.get(key)
        a_norm = _normalize_value(a_val, field_name=key)
        b_norm = _normalize_value(b_val, field_name=key)
        if a_norm == b_norm:
            continue
        if isinstance(a_norm, dict) and isinstance(b_norm, dict):
            deltas.extend(
                _diff_dict(
                    a_norm,
                    b_norm,
                    parent_field=path,
                    ignore_fields=ignore_fields,
                ),
            )
        else:
            deltas.append(FieldDelta(field=path, before=a_val, after=b_val))
    return deltas


def _normalize_value(value: Any, *, field_name: str) -> Any:
    """§5.1 normalization: strip strings, treat None/NaN/'' equivalently,
    sort order-insensitive list fields by repr."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and field_name in ORDER_INSENSITIVE_LIST_FIELDS:
        return sorted((_normalize_value(v, field_name="") for v in value), key=repr)
    return value
