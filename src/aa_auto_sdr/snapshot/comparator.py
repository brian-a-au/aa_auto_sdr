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
    Comparability,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)
from aa_auto_sdr.snapshot.schema import captured_before

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


# Fields not collected for dimensions and metrics before 1.21.25 (the SDK's
# default DataFrame selection dropped them). Against an older capture their
# deltas are an artifact of the capture, not a change in Adobe Analytics.
_LEGACY_UNCOLLECTED_FIELDS: frozenset[str] = frozenset({"tags", "data_group", "extra"})
_LEGACY_UNCOLLECTED_FAMILIES = ("dimensions", "metrics")
_LEGACY_FIELDS_COLLECTED_IN = (1, 21, 25)


def legacy_uncollected_fields(a_tool_version: Any, b_tool_version: Any, effective_ignore: frozenset[str]) -> list[str]:
    """Dimension and metric fields not compared because either side's capture
    predates their collection (empty when both are current or the fields are
    already ignored)."""
    legacy = any(
        captured_before({"tool_version": v}, _LEGACY_FIELDS_COLLECTED_IN) for v in (a_tool_version, b_tool_version)
    )
    return sorted(_LEGACY_UNCOLLECTED_FIELDS - effective_ignore) if legacy else []


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
    legacy_skipped = legacy_uncollected_fields(a.get("tool_version"), b.get("tool_version"), effective_ignore)

    rs_deltas = _diff_dict(
        a_components["report_suite"],
        b_components["report_suite"],
        parent_field="",
        ignore_fields=effective_ignore,
    )

    components: list[ComponentDiff] = []
    for ctype in _COMPONENT_TYPES:
        family_ignore = effective_ignore
        if legacy_skipped and ctype in _LEGACY_UNCOLLECTED_FAMILIES:
            family_ignore = effective_ignore | _LEGACY_UNCOLLECTED_FIELDS
        cd = _diff_component_list(
            ctype,
            a_components.get(ctype, []),
            b_components.get(ctype, []),
            ignore_fields=family_ignore,
        )
        comparability, reason = _suppression_for(ctype, a, b)
        if comparability in ("excluded", "unknown"):
            # One side holds no data for this family, so the raw lists are an
            # artifact of the gap, not evidence. Degraded and partial sections
            # keep their raw rows (both sides were fetched).
            cd = ComponentDiff(
                component_type=ctype,
                suppressed=True,
                suppression_reason=reason,
                comparability=comparability,
            )
        elif comparability != "comparable":
            cd = dataclasses.replace(cd, suppressed=True, suppression_reason=reason, comparability=comparability)
        components.append(cd)

    # Families one capture collected and the other did not: their changes in
    # the gap are never compared, so say so once per comparison.
    not_compared = sorted(
        c.component_type
        for c in components
        if c.comparability == "excluded" and c.suppression_reason != "not collected in either snapshot"
    )
    if not_compared:
        rsid = b.get("rsid") or a.get("rsid") or ""
        logger.warning(
            "diff_scope_mismatch rsid=%s not_compared=%s; changes to these families since the last "
            "capture that collected them are not reported",
            rsid,
            ",".join(not_compared),
            extra={"rsid": rsid, "not_compared": not_compared},
        )

    if legacy_skipped:
        rsid = b.get("rsid") or a.get("rsid") or ""
        logger.warning(
            "diff_legacy_capture_fields rsid=%s not_compared_fields=%s; a capture older than 1.21.25 did not "
            "collect these dimension and metric fields, so they are not compared",
            rsid,
            ",".join(legacy_skipped),
            extra={"rsid": rsid, "not_compared_fields": legacy_skipped},
        )

    report = DiffReport(
        a_rsid=a["rsid"],
        b_rsid=b["rsid"],
        a_captured_at=a["captured_at"],
        b_captured_at=b["captured_at"],
        a_tool_version=a["tool_version"],
        b_tool_version=b["tool_version"],
        report_suite_deltas=rs_deltas,
        settings_changes=len(rs_deltas),
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
) -> tuple[Comparability, str | None]:
    """Decide whether a section is comparable. Returns (comparability, reason).

    Capture scope is checked first: a family one side did not collect is never
    diffed, so filtered captures cannot produce false additions or removals.
    A legacy side (no `collected_components`) counts as collected when it has
    rows; an empty legacy family against rows cannot be told apart from an
    exclusion, so it is suppressed as unknown, after the spec §4.7 degraded and
    partial rules, which name a more specific cause. Two legacy sides diff
    normally.
    """
    left_scope = _scope_of(component_type, a)
    right_scope = _scope_of(component_type, b)
    if left_scope == "excluded" and right_scope == "excluded":
        return "excluded", "not collected in either snapshot"
    if left_scope == "excluded":
        return "excluded", "not collected in source"
    if right_scope == "excluded":
        return "excluded", "not collected in target"

    left_degraded = component_type in a.get("degraded_components", [])
    right_degraded = component_type in b.get("degraded_components", [])
    if left_degraded or right_degraded:
        return "degraded", "fetch degraded"
    left_level = a.get("partial_components", {}).get(component_type)
    right_level = b.get("partial_components", {}).get(component_type)
    if left_level != right_level:
        return "partial", f"fetch partial (expansion_level={left_level or right_level})"
    # Same partial level on both sides is comparable; only scope can still block it.

    left_rows = bool(a["components"].get(component_type))
    right_rows = bool(b["components"].get(component_type))
    # Two scope-less sides are both full captures: released CLIs never wrote
    # filtered snapshots, so only a single scope-less side is ambiguous.
    if left_scope == right_scope == "unknown":
        return "comparable", None
    if (left_scope == "unknown" and not left_rows and right_rows) or (
        right_scope == "unknown" and not right_rows and left_rows
    ):
        return "unknown", "capture scope unknown (legacy snapshot)"
    return "comparable", None


def _scope_of(component_type: str, env: dict[str, Any]) -> str:
    """`collected`, `excluded`, or `unknown` (legacy envelope without scope)."""
    collected = env.get("collected_components")
    if collected is None:
        return "unknown"
    return "collected" if component_type in collected else "excluded"


def _diff_dict(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    parent_field: str,
    ignore_fields: frozenset[str] = frozenset(),
) -> list[FieldDelta]:
    """Walk two dicts and emit FieldDelta for each leaf inequality, after normalization.

    Root-level `id` and `rsid` are identity fields; mismatches surface via the parent
    DiffReport's added/removed lists or `rsid_mismatch` flag, so we skip them
    here to avoid emitting redundant deltas. Nested references with those names
    are definition data and must still be compared."""
    deltas: list[FieldDelta] = []
    keys = sorted(a.keys() | b.keys())
    for key in keys:
        if not parent_field and key in ("id", "rsid"):
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
