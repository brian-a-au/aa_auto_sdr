"""Diff data model for snapshot comparison.

Boundary types: pure data, no I/O. Produced by snapshot.comparator.compare;
consumed by output.diff_renderers.*."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Comparability = Literal["comparable", "excluded", "unknown", "degraded", "partial"]


@dataclass(frozen=True, slots=True)
class FieldDelta:
    """A single field-level change between two component versions."""

    field: str  # "name", "type", "tags[2]", "definition.condition", etc.
    before: Any  # JSON-serializable
    after: Any  # JSON-serializable


@dataclass(frozen=True, slots=True)
class AddedRemovedItem:
    """A component present in only one of source/target."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ModifiedItem:
    """A component present in both, with field-level deltas."""

    id: str
    name: str  # display name of the *target* (post-change)
    deltas: list[FieldDelta] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ComponentDiff:
    """Per-component-type diff result. One per component type in DiffReport.

    `suppressed=True` (v1.7.1+) means the section is hidden from rendering
    because either side's snapshot was degraded or partial-with-mismatched-
    expansion-level. Renderers branch on `suppressed` and emit a single
    annotation in place of per-row tables. JSON renderer's serialized shape
    is unchanged-but-additive: existing fields preserved, new fields appear.
    See spec §4.7.

    `comparability` names why a section is or is not comparable:
    `comparable`, `excluded` (a side did not collect the family), `unknown`
    (a legacy side has no scope and an empty family against rows),
    `degraded`, or `partial`. Every value other than `comparable` comes with
    `suppressed=True`.
    """

    component_type: str  # "dimensions", "metrics", "segments", ...
    added: list[AddedRemovedItem] = field(default_factory=list)
    removed: list[AddedRemovedItem] = field(default_factory=list)
    modified: list[ModifiedItem] = field(default_factory=list)
    unchanged_count: int = 0
    suppressed: bool = False
    suppression_reason: str | None = None
    comparability: Comparability = "comparable"


@dataclass(frozen=True, slots=True)
class DiffReport:
    """Aggregated diff between two SdrDocument-equivalent envelopes."""

    a_rsid: str
    b_rsid: str
    a_captured_at: str  # ISO from envelope, unchanged
    b_captured_at: str
    a_tool_version: str
    b_tool_version: str
    report_suite_deltas: list[FieldDelta] = field(default_factory=list)
    components: list[ComponentDiff] = field(default_factory=list)
    rsid_mismatch: bool = False
    # Changed report-suite fields, one per field. Kept apart from component
    # churn: it never enters component totals or the warn/watch thresholds.
    settings_changes: int = 0
    # `captured_at` of newer snapshots skipped while choosing a covering
    # baseline (watch, --compare-with-prev); empty for explicit --diff tokens.
    baseline_skipped: list[str] = field(default_factory=list)
