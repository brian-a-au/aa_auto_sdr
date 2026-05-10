"""Trending renderers — console, json, markdown."""

from __future__ import annotations

import json as _json
from datetime import UTC, datetime

from aa_auto_sdr.snapshot.trending import (
    _COMPONENT_TYPES,
    ComponentCounts,
    DriftSummary,
    LifecycleDelta,
    SnapshotPoint,
    TrendingReport,
    WindowSpec,
)


def _sample_report(rsid: str = "rs1") -> TrendingReport:
    ts1 = datetime(2026, 5, 1, 8, 0, tzinfo=UTC)
    ts2 = datetime(2026, 5, 8, 8, 0, tzinfo=UTC)
    delta = {ct: LifecycleDelta() for ct in _COMPONENT_TYPES}
    delta["dimensions"] = LifecycleDelta(added=1, removed=0, modified=0, unchanged=100)
    return TrendingReport(
        rsid=rsid,
        name=rsid.upper(),
        window=WindowSpec(
            duration="30d",
            start_at=datetime(2026, 4, 10, tzinfo=UTC),
            end_at=datetime(2026, 5, 10, tzinfo=UTC),
        ),
        series=[
            SnapshotPoint(
                captured_at=ts1,
                tool_version="1.13.0",
                counts=ComponentCounts(dimensions=100),
                delta_by_type=None,
            ),
            SnapshotPoint(
                captured_at=ts2,
                tool_version="1.13.0",
                counts=ComponentCounts(dimensions=101),
                delta_by_type=delta,
            ),
        ],
        drift=DriftSummary(
            total_changes=1,
            volatility_score=0.01,
            most_active_component_type="dimensions",
            churn_by_component_type=dict(zip(_COMPONENT_TYPES, [1, 0, 0, 0, 0, 0], strict=False)),
        ),
    )


class TestConsoleRenderer:
    def test_renders_header_with_rsid_and_name(self) -> None:
        from aa_auto_sdr.output.trending_renderers.console import render_console

        out = render_console([_sample_report()])
        assert "rs1" in out
        assert "RS1" in out
        assert "30d" in out

    def test_renders_one_row_per_snapshot(self) -> None:
        from aa_auto_sdr.output.trending_renderers.console import render_console

        out = render_console([_sample_report()])
        # Both timestamps appear (formatted as table rows).
        assert "2026-05-01" in out
        assert "2026-05-08" in out

    def test_renders_drift_summary_footer(self) -> None:
        from aa_auto_sdr.output.trending_renderers.console import render_console

        out = render_console([_sample_report()])
        assert "DRIFT SUMMARY" in out
        assert "0.01" in out  # volatility_score
        assert "dimensions" in out  # most_active_component_type

    def test_multi_rsid_renders_per_rsid_blocks(self) -> None:
        from aa_auto_sdr.output.trending_renderers.console import render_console

        out = render_console([_sample_report("rs1"), _sample_report("rs2")])
        assert "rs1" in out
        assert "rs2" in out
        # Two TRENDING WINDOW headers, one per RSID.
        assert out.count("TRENDING WINDOW") == 2


class TestJsonRenderer:
    def test_single_rsid_emits_top_level_report(self) -> None:
        from aa_auto_sdr.output.trending_renderers.json import render_json

        out = render_json([_sample_report()])
        payload = _json.loads(out)
        assert payload["schema"] == "aa-trending/v1"
        assert payload["rsid"] == "rs1"
        assert payload["window"]["duration"] == "30d"
        assert len(payload["series"]) == 2
        assert payload["drift"]["total_changes"] == 1

    def test_multi_rsid_wraps_in_reports_array(self) -> None:
        from aa_auto_sdr.output.trending_renderers.json import render_json

        out = render_json([_sample_report("rs1"), _sample_report("rs2")])
        payload = _json.loads(out)
        assert payload["schema"] == "aa-trending/v1"
        assert "reports" in payload
        assert len(payload["reports"]) == 2
        assert payload["reports"][0]["rsid"] == "rs1"
        assert payload["reports"][1]["rsid"] == "rs2"


class TestMarkdownRenderer:
    def test_renders_h1_per_rsid(self) -> None:
        from aa_auto_sdr.output.trending_renderers.markdown import render_markdown

        out = render_markdown([_sample_report()])
        assert "# Trending: rs1" in out

    def test_renders_table_with_pipe_separators(self) -> None:
        from aa_auto_sdr.output.trending_renderers.markdown import render_markdown

        out = render_markdown([_sample_report()])
        # Markdown table syntax — rough check.
        assert "|" in out
        assert "---" in out  # alignment row

    def test_renders_drift_section(self) -> None:
        from aa_auto_sdr.output.trending_renderers.markdown import render_markdown

        out = render_markdown([_sample_report()])
        assert "## Drift" in out
        assert "0.01" in out
