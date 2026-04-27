"""Snapshot diff algorithm — pure, takes two envelope dicts, returns a DiffReport.

Adopts two patterns from cja_auto_sdr/diff/comparator.py (audited 2026-04-26):
  * generic ID-keyed loop with parameterized field-allowlist
  * value normalization (whitespace strip, NaN/None/'' equivalence,
    order-insensitive 'tags'/'categories')

See v0.7 design spec §5 + §5.1 for design rationale."""

from __future__ import annotations

import math
from typing import Any

from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)

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


def compare(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    ignore_fields: frozenset[str] = frozenset(),
) -> DiffReport:
    """Diff two snapshot envelopes (assumed schema-validated by the caller).

    `ignore_fields` is a set of field names to skip during compare. The match is
    exact at every nesting level — `description` skips both top-level and nested
    `description` fields."""
    a_components = a["components"]
    b_components = b["components"]

    rs_deltas = _diff_dict(
        a_components["report_suite"],
        b_components["report_suite"],
        parent_field="",
        ignore_fields=ignore_fields,
    )

    components: list[ComponentDiff] = [
        _diff_component_list(
            ctype,
            a_components.get(ctype, []),
            b_components.get(ctype, []),
            ignore_fields=ignore_fields,
        )
        for ctype in _COMPONENT_TYPES
    ]

    return DiffReport(
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
