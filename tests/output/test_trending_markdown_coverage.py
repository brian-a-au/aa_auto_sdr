"""Targeted coverage for the trending markdown renderer.

Covers the multi-report separator, the empty-series message, and the
drift-not-computed branch."""

from __future__ import annotations

from datetime import UTC, datetime

from aa_auto_sdr.output.trending_renderers.markdown import render_markdown
from aa_auto_sdr.snapshot.trending import (
    ComponentCounts,
    SnapshotPoint,
    TrendingReport,
    WindowSpec,
)


def _window() -> WindowSpec:
    return WindowSpec(
        duration="30d",
        start_at=datetime(2026, 4, 10, tzinfo=UTC),
        end_at=datetime(2026, 5, 10, tzinfo=UTC),
    )


def _point() -> SnapshotPoint:
    return SnapshotPoint(
        captured_at=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
        tool_version="1.13.0",
        counts=ComponentCounts(dimensions=5),
        delta_by_type=None,
    )


def _report_no_drift(rsid: str = "rs1") -> TrendingReport:
    return TrendingReport(rsid=rsid, name="RS1", window=_window(), series=[_point()], drift=None)


def _report_no_series(rsid: str = "rs0") -> TrendingReport:
    return TrendingReport(rsid=rsid, name="", window=_window(), series=[], drift=None)


def test_multi_report_separator_between_reports() -> None:
    out = render_markdown([_report_no_drift("rs1"), _report_no_drift("rs2")])
    assert "\n---\n\n" in out  # separator before the second report
    assert "# Trending: rs1" in out
    assert "# Trending: rs2" in out


def test_empty_series_renders_no_snapshots_message() -> None:
    out = render_markdown([_report_no_series()])
    assert "_No snapshots in window._" in out


def test_drift_none_renders_not_computed() -> None:
    out = render_markdown([_report_no_drift()])
    assert "_Drift not computed._" in out
