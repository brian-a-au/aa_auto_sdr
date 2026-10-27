"""Per-RSID drift / trending windows over a series of snapshots.

Reads existing snapshot files via `snapshot/store.py::list_snapshots` and
runs pairwise `snapshot/comparator.py::compare` between consecutive
snapshots in the window. No AA API contact; no SDR rebuild.

See `docs/superpowers/specs/2026-05-10-aa-auto-sdr-v1.13.0-design.md`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aa_auto_sdr.snapshot.baseline import covers, scope_of, select_covering
from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.models import Comparability, ComponentDiff
from aa_auto_sdr.snapshot.retention import restore_iso
from aa_auto_sdr.snapshot.store import list_snapshots, load_snapshot

logger = logging.getLogger(__name__)

_COMPONENT_TYPES = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
)


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """User-supplied window resolved into concrete bounds."""

    duration: str  # e.g. "30d"
    start_at: datetime  # window lower bound (inclusive)
    end_at: datetime  # window upper bound (typically "now" at compute time)


@dataclass(frozen=True, slots=True)
class ComponentCounts:
    """Per-component-type counts on a single snapshot."""

    dimensions: int = 0
    metrics: int = 0
    segments: int = 0
    calculated_metrics: int = 0
    virtual_report_suites: int = 0
    classifications: int = 0

    def total(self) -> int:
        return (
            self.dimensions
            + self.metrics
            + self.segments
            + self.calculated_metrics
            + self.virtual_report_suites
            + self.classifications
        )


@dataclass(frozen=True, slots=True)
class LifecycleDelta:
    """Pairwise diff summary between two consecutive snapshots."""

    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0
    comparability: Comparability = "comparable"
    suppression_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotPoint:
    """One snapshot in the window with its components and (optional) delta-from-prev."""

    captured_at: datetime
    tool_version: str
    counts: ComponentCounts
    delta_by_type: dict[str, LifecycleDelta] | None = None  # None for the first point
    settings_changes: int | None = None  # changed report-suite fields vs prev; None for the first point
    # The earlier snapshot this point was compared against: the newest one whose
    # scope covers this point's. None when no earlier snapshot covers it.
    baseline_captured_at: datetime | None = None
    # This point's capture scope (sorted family names); None for legacy snapshots.
    collected_components: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class DriftSummary:
    """Always computed; always included in output. No opt-in flag."""

    total_changes: int
    volatility_score: float  # 0.0–1.0
    most_active_component_type: str | None
    churn_by_component_type: dict[str, int] = field(default_factory=dict)
    settings_changes: int = 0  # report-suite field changes; never part of total_changes


@dataclass(frozen=True, slots=True)
class TrendingReport:
    rsid: str
    name: str | None
    window: WindowSpec
    series: list[SnapshotPoint] = field(default_factory=list)
    drift: DriftSummary | None = None  # populated by compute_trending


def _summarize_diff(cd: ComponentDiff) -> LifecycleDelta:
    """Flatten ComponentDiff into a 4-count LifecycleDelta. Suppressed
    sections contribute zeros — we don't want degraded fetches or filtered
    captures to inflate drift scores — and keep their comparability and
    reason so renderers can say the family was not comparable."""
    if cd.suppressed:
        return LifecycleDelta(comparability=cd.comparability, suppression_reason=cd.suppression_reason)
    return LifecycleDelta(
        added=len(cd.added),
        removed=len(cd.removed),
        modified=len(cd.modified),
        unchanged=cd.unchanged_count,
    )


def not_comparable_by_reason(point: SnapshotPoint) -> dict[str, list[str]]:
    """Group a point's non-comparable families by reason, for renderer footnotes."""
    grouped: dict[str, list[str]] = {}
    for ct, delta in (point.delta_by_type or {}).items():
        if delta.comparability != "comparable":
            grouped.setdefault(delta.suppression_reason or delta.comparability, []).append(ct)
    return grouped


def _compute_drift_summary(series: list[SnapshotPoint]) -> DriftSummary:
    """Compute drift summary across a series of SnapshotPoints.

    `volatility_score = total_changes / (starting_components * n_pairs)`,
    clamped to [0.0, 1.0]. Empty / single-snapshot series → zero drift.

    Only counted points contribute (and `n_pairs` counts only them): a point
    with no delta is skipped, and so is a point superseded by a later one that
    compared against the same baseline and covers its scope. Otherwise a
    filtered snapshot between two full ones would count its families'
    changes twice (once itself, once again in the next full point).
    """
    if len(series) < 2:
        return DriftSummary(
            total_changes=0,
            volatility_score=0.0,
            most_active_component_type=None,
            churn_by_component_type=dict.fromkeys(_COMPONENT_TYPES, 0),
        )

    counted = _drift_points(series)
    churn_by_type: dict[str, int] = dict.fromkeys(_COMPONENT_TYPES, 0)
    for point in counted:
        for ct, delta in (point.delta_by_type or {}).items():
            churn_by_type[ct] += delta.added + delta.removed + delta.modified

    total_changes = sum(churn_by_type.values())
    starting_components = series[0].counts.total()
    n_pairs = len(counted)

    if starting_components == 0 or n_pairs == 0:
        volatility = 0.0
    else:
        volatility = total_changes / (starting_components * n_pairs)
        volatility = min(1.0, volatility)  # clamp

    most_active = max(churn_by_type.items(), key=lambda kv: kv[1])[0] if total_changes > 0 else None

    return DriftSummary(
        total_changes=total_changes,
        volatility_score=round(volatility, 3),
        most_active_component_type=most_active,
        churn_by_component_type=churn_by_type,
        settings_changes=sum(point.settings_changes or 0 for point in counted),
    )


def _drift_points(series: list[SnapshotPoint]) -> list[SnapshotPoint]:
    """Points whose deltas enter drift (see `_compute_drift_summary`)."""
    counted: list[SnapshotPoint] = []
    for i, point in enumerate(series):
        if point.delta_by_type is None:
            continue
        superseded = point.baseline_captured_at is not None and any(
            later.baseline_captured_at == point.baseline_captured_at
            and covers(later.collected_components, point.collected_components)
            for later in series[i + 1 :]
        )
        if not superseded:
            counted.append(point)
    return counted


def compute_trending(
    *,
    snapshot_dir: Path,
    rsid: str,
    window: WindowSpec,
    extended_fields: bool = False,
    ignore_fields: tuple[str, ...] = (),
) -> TrendingReport:
    """Load all snapshots for `rsid` falling within `window`, run pairwise
    `compare()` between consecutive snapshots, return a TrendingReport.

    Reads filesystem only — no AA API calls. Returns a TrendingReport with
    empty `series` when no snapshots fall in the window (caller decides
    whether that's user-facing error).
    """
    paths = list_snapshots(snapshot_dir, rsid=rsid)
    matching = [p for p in paths if _path_in_window(p, window)]

    series: list[SnapshotPoint] = []
    # Latest envelope per distinct scope, oldest first. Each point is compared
    # against the newest earlier snapshot whose scope covers it, so a filtered
    # snapshot never becomes the baseline of a fuller one. Bounded by the
    # number of distinct scopes, not the window size.
    latest_by_scope: dict[tuple[str, ...] | None, dict[str, Any]] = {}
    last = None
    for p in matching:
        snap = load_snapshot(p)
        delta_by_type: dict[str, LifecycleDelta] | None = None
        settings_changes: int | None = None
        baseline_at: datetime | None = None
        choice = select_covering(reversed(list(latest_by_scope.values())), scope_of(snap))
        if choice.envelope is not None:
            diff = compare(
                a=choice.envelope,
                b=snap,
                ignore_fields=frozenset(ignore_fields),
                extended_fields=extended_fields,
            )
            delta_by_type = {cd.component_type: _summarize_diff(cd) for cd in diff.components}
            settings_changes = diff.settings_changes
            if isinstance(choice.envelope.get("captured_at"), str):
                baseline_at = datetime.fromisoformat(choice.envelope["captured_at"])
        series.append(_to_snapshot_point(snap, delta_by_type, settings_changes, baseline_at))
        scope = scope_of(snap)
        key = tuple(sorted(scope)) if scope is not None else None
        latest_by_scope.pop(key, None)
        latest_by_scope[key] = snap
        last = snap

    drift = _compute_drift_summary(series)
    name = _name_from_envelope(last) if last is not None else None

    # Message keys align with extras keys exactly. v1.12.1 added word-boundary
    # matching to the vocabulary validator (Rule 2 at test_logging_vocabulary
    # now uses (?:^|\W){key}=), so substrings like `count=` inside
    # `snapshot_count=` no longer false-positive against VOCAB.
    logger.info(
        "trending_compute_complete rsid=%s snapshot_count=%s total_changes=%s volatility_score=%s",
        rsid,
        len(series),
        drift.total_changes,
        drift.volatility_score,
        extra={
            "rsid": rsid,
            "snapshot_count": len(series),
            "total_changes": drift.total_changes,
            "volatility_score": drift.volatility_score,
        },
    )
    return TrendingReport(rsid=rsid, name=name, window=window, series=series, drift=drift)


def _path_in_window(path: Path, window: WindowSpec) -> bool:
    """Return True if the snapshot file's stem-derived timestamp is within window.

    Reuses `retention.restore_iso` (promoted to public in v1.13.0) so
    we don't have to load the JSON envelope just to check the timestamp.
    """
    captured = restore_iso(path.stem)
    return window.start_at <= captured <= window.end_at


def _to_snapshot_point(
    envelope: dict[str, Any],
    delta_by_type: dict[str, LifecycleDelta] | None,
    settings_changes: int | None = None,
    baseline_captured_at: datetime | None = None,
) -> SnapshotPoint:
    """Convert a snapshot envelope dict into a SnapshotPoint."""
    components = envelope.get("components", {})
    counts = ComponentCounts(
        dimensions=len(components.get("dimensions", [])),
        metrics=len(components.get("metrics", [])),
        segments=len(components.get("segments", [])),
        calculated_metrics=len(components.get("calculated_metrics", [])),
        virtual_report_suites=len(components.get("virtual_report_suites", [])),
        classifications=len(components.get("classifications", [])),
    )
    captured_str = envelope.get("captured_at", "")
    captured = datetime.fromisoformat(captured_str)
    return SnapshotPoint(
        captured_at=captured,
        tool_version=envelope.get("tool_version", ""),
        counts=counts,
        delta_by_type=delta_by_type,
        settings_changes=settings_changes,
        baseline_captured_at=baseline_captured_at,
        collected_components=tuple(sorted(scope)) if (scope := scope_of(envelope)) is not None else None,
    )


def _name_from_envelope(envelope: dict[str, Any]) -> str | None:
    components = envelope.get("components", {})
    rs = components.get("report_suite", {})
    return rs.get("name")
