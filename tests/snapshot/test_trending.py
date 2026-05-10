"""TrendingReport dataclasses + math helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.snapshot.models import AddedRemovedItem, ComponentDiff, ModifiedItem
from aa_auto_sdr.snapshot.trending import (
    _COMPONENT_TYPES,
    ComponentCounts,
    DriftSummary,
    LifecycleDelta,
    SnapshotPoint,
    WindowSpec,
    _compute_drift_summary,
    _summarize_diff,
)


class TestComponentTypes:
    def test_six_canonical_types(self) -> None:
        assert _COMPONENT_TYPES == (
            "dimensions",
            "metrics",
            "segments",
            "calculated_metrics",
            "virtual_report_suites",
            "classifications",
        )


class TestSummarizeDiff:
    def test_empty_component_diff(self) -> None:
        cd = ComponentDiff(component_type="dimensions")
        result = _summarize_diff(cd)
        assert result == LifecycleDelta(added=0, removed=0, modified=0, unchanged=0)

    def test_counts_from_lists(self) -> None:
        cd = ComponentDiff(
            component_type="metrics",
            added=[
                AddedRemovedItem(id="m1", name="metric_one"),
                AddedRemovedItem(id="m2", name="metric_two"),
            ],
            removed=[AddedRemovedItem(id="m3", name="old_metric")],
            modified=[ModifiedItem(id="m4", name="changed_metric", deltas=[])],
            unchanged_count=42,
        )
        result = _summarize_diff(cd)
        assert result == LifecycleDelta(added=2, removed=1, modified=1, unchanged=42)

    def test_suppressed_component_diff_returns_zeros(self) -> None:
        # Suppressed sections (degraded/partial) should not contribute to drift counts.
        cd = ComponentDiff(
            component_type="dimensions",
            suppressed=True,
            suppression_reason="degraded",
        )
        result = _summarize_diff(cd)
        assert result == LifecycleDelta(added=0, removed=0, modified=0, unchanged=0)


def _point(
    captured_at: datetime,
    *,
    counts: ComponentCounts | None = None,
    delta: dict[str, LifecycleDelta] | None = None,
) -> SnapshotPoint:
    return SnapshotPoint(
        captured_at=captured_at,
        tool_version="1.13.0",
        counts=counts or ComponentCounts(),
        delta_by_type=delta,
    )


class TestComputeDriftSummary:
    def test_empty_series_is_zero_drift(self) -> None:
        result = _compute_drift_summary([])
        assert result == DriftSummary(
            total_changes=0,
            volatility_score=0.0,
            most_active_component_type=None,
            churn_by_component_type=dict.fromkeys(_COMPONENT_TYPES, 0),
        )

    def test_single_snapshot_is_zero_drift(self) -> None:
        result = _compute_drift_summary([_point(datetime(2026, 5, 1, tzinfo=UTC))])
        assert result.total_changes == 0
        assert result.volatility_score == 0.0
        assert result.most_active_component_type is None

    def test_two_snapshots_no_changes_zero_drift(self) -> None:
        ts = datetime(2026, 5, 1, tzinfo=UTC)
        starting = ComponentCounts(dimensions=100, metrics=50)
        zero_delta = {ct: LifecycleDelta() for ct in _COMPONENT_TYPES}
        result = _compute_drift_summary(
            [
                _point(ts, counts=starting),
                _point(ts, counts=starting, delta=zero_delta),
            ]
        )
        assert result.total_changes == 0
        assert result.volatility_score == 0.0
        assert result.most_active_component_type is None

    def test_two_snapshots_one_addition(self) -> None:
        ts = datetime(2026, 5, 1, tzinfo=UTC)
        starting = ComponentCounts(dimensions=100, metrics=50)
        delta = {ct: LifecycleDelta() for ct in _COMPONENT_TYPES}
        delta["dimensions"] = LifecycleDelta(added=1, removed=0, modified=0, unchanged=100)
        result = _compute_drift_summary(
            [
                _point(ts, counts=starting),
                _point(ts, counts=ComponentCounts(dimensions=101, metrics=50), delta=delta),
            ]
        )
        assert result.total_changes == 1
        # 1 change / (150 starting components * 1 pair) ≈ 0.007
        assert 0.0 < result.volatility_score < 0.01
        assert result.most_active_component_type == "dimensions"
        assert result.churn_by_component_type["dimensions"] == 1

    def test_volatility_clamps_at_one(self) -> None:
        """If churn vastly exceeds starting size, volatility caps at 1.0."""
        ts = datetime(2026, 5, 1, tzinfo=UTC)
        starting = ComponentCounts(dimensions=10)
        # 100 changes on a starting size of 10 → ratio 10.0, clamped to 1.0.
        delta = {ct: LifecycleDelta() for ct in _COMPONENT_TYPES}
        delta["dimensions"] = LifecycleDelta(added=100, removed=0, modified=0, unchanged=10)
        result = _compute_drift_summary(
            [
                _point(ts, counts=starting),
                _point(ts, counts=starting, delta=delta),
            ]
        )
        assert result.volatility_score == 1.0

    def test_zero_starting_components_yields_zero_volatility(self) -> None:
        """Edge case: empty first snapshot. volatility_score must not divide by zero."""
        ts = datetime(2026, 5, 1, tzinfo=UTC)
        delta = {ct: LifecycleDelta() for ct in _COMPONENT_TYPES}
        delta["dimensions"] = LifecycleDelta(added=5, removed=0, modified=0, unchanged=0)
        result = _compute_drift_summary(
            [
                _point(ts, counts=ComponentCounts()),  # all zeros
                _point(ts, counts=ComponentCounts(dimensions=5), delta=delta),
            ]
        )
        assert result.volatility_score == 0.0
        assert result.total_changes == 5

    def test_most_active_picks_max_churn_type(self) -> None:
        ts = datetime(2026, 5, 1, tzinfo=UTC)
        starting = ComponentCounts(dimensions=100, metrics=100, segments=100)
        delta = {ct: LifecycleDelta() for ct in _COMPONENT_TYPES}
        delta["dimensions"] = LifecycleDelta(added=2, removed=0, modified=0, unchanged=100)
        delta["metrics"] = LifecycleDelta(added=0, removed=0, modified=5, unchanged=95)
        delta["segments"] = LifecycleDelta(added=1, removed=1, modified=0, unchanged=98)
        result = _compute_drift_summary(
            [
                _point(ts, counts=starting),
                _point(ts, counts=starting, delta=delta),
            ]
        )
        # metrics had 5 changes — highest of the three.
        assert result.most_active_component_type == "metrics"
        assert result.churn_by_component_type == {
            "dimensions": 2,
            "metrics": 5,
            "segments": 2,
            "calculated_metrics": 0,
            "virtual_report_suites": 0,
            "classifications": 0,
        }


class TestComputeTrending:
    """compute_trending against a tmp_path snapshot store."""

    def _write_snapshot(
        self,
        snapshot_dir: Path,
        rsid: str,
        captured_at: datetime,
        *,
        dimensions: list[dict] | None = None,
        metrics: list[dict] | None = None,
    ) -> Path:
        """Write a minimal v4 envelope to <snapshot_dir>/<rsid>/<ts>.json."""
        import json

        target_dir = snapshot_dir / rsid
        target_dir.mkdir(parents=True, exist_ok=True)
        # fs-safe stem: ISO with colons → hyphens (matches store.py convention).
        stem = captured_at.isoformat().replace(":", "-")
        target = target_dir / f"{stem}.json"
        envelope = {
            "schema": "aa-sdr-snapshot/v4",
            "rsid": rsid,
            "captured_at": captured_at.isoformat(),
            "tool_version": "1.13.0",
            "degraded_components": [],
            "partial_components": {},
            "quality": None,
            "components": {
                "report_suite": {"rsid": rsid, "name": rsid.upper()},
                "dimensions": dimensions or [],
                "metrics": metrics or [],
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
            },
        }
        target.write_text(json.dumps(envelope))
        return target

    def test_empty_window_returns_empty_series(self, tmp_path: Path) -> None:
        from aa_auto_sdr.snapshot.trending import compute_trending

        window = WindowSpec(
            duration="30d",
            start_at=datetime(2026, 4, 10, tzinfo=UTC),
            end_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        report = compute_trending(snapshot_dir=tmp_path, rsid="rs_missing", window=window)
        assert report.rsid == "rs_missing"
        assert report.name is None
        assert report.series == []
        assert report.drift.total_changes == 0
        assert report.drift.volatility_score == 0.0

    def test_single_snapshot_in_window(self, tmp_path: Path) -> None:
        from aa_auto_sdr.snapshot.trending import compute_trending

        ts = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
        self._write_snapshot(
            tmp_path,
            "rs1",
            ts,
            dimensions=[{"id": "evar1", "name": "page", "type": "string"}],
        )
        window = WindowSpec(
            duration="30d",
            start_at=datetime(2026, 4, 10, tzinfo=UTC),
            end_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window)
        assert len(report.series) == 1
        assert report.series[0].counts.dimensions == 1
        assert report.series[0].delta_by_type is None  # first point — no prev
        assert report.drift.total_changes == 0
        assert report.name == "RS1"

    def test_two_snapshots_one_addition(self, tmp_path: Path) -> None:
        from aa_auto_sdr.snapshot.trending import compute_trending

        ts1 = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
        ts2 = datetime(2026, 5, 8, 8, 0, tzinfo=UTC)
        self._write_snapshot(
            tmp_path,
            "rs1",
            ts1,
            dimensions=[{"id": "evar1", "name": "page", "type": "string"}],
        )
        self._write_snapshot(
            tmp_path,
            "rs1",
            ts2,
            dimensions=[
                {"id": "evar1", "name": "page", "type": "string"},
                {"id": "evar2", "name": "section", "type": "string"},
            ],
        )
        window = WindowSpec(
            duration="30d",
            start_at=datetime(2026, 4, 10, tzinfo=UTC),
            end_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window)
        assert len(report.series) == 2
        assert report.series[0].delta_by_type is None
        assert report.series[1].delta_by_type is not None
        assert report.series[1].delta_by_type["dimensions"].added == 1
        assert report.drift.total_changes == 1
        assert report.drift.most_active_component_type == "dimensions"

    def test_window_excludes_old_snapshots(self, tmp_path: Path) -> None:
        from aa_auto_sdr.snapshot.trending import compute_trending

        # Snapshot 60 days ago — outside a 30d window.
        old_ts = datetime(2026, 3, 10, 8, 0, tzinfo=UTC)
        new_ts = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
        self._write_snapshot(tmp_path, "rs1", old_ts)
        self._write_snapshot(tmp_path, "rs1", new_ts)
        window = WindowSpec(
            duration="30d",
            start_at=datetime(2026, 4, 10, tzinfo=UTC),
            end_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window)
        # Only new_ts is in window.
        assert len(report.series) == 1
        assert report.series[0].captured_at == new_ts
