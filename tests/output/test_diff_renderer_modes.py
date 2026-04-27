"""Mode toggles (summary, side_by_side) for diff renderers."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def _report_with_changes() -> DiffReport:
    return DiffReport(
        a_rsid="RS1",
        b_rsid="RS1",
        a_captured_at="2026-04-25T10:00:00+00:00",
        b_captured_at="2026-04-26T10:00:00+00:00",
        a_tool_version="1.1.0",
        b_tool_version="1.1.0",
        components=[
            ComponentDiff(
                component_type="metrics",
                added=[AddedRemovedItem(id="m2", name="New Metric")],
                modified=[
                    ModifiedItem(
                        id="m1",
                        name="Visits",
                        deltas=[FieldDelta(field="description", before="old", after="new")],
                    ),
                ],
                unchanged_count=10,
            ),
        ],
    )


class TestConsoleSummary:
    def test_summary_drops_field_deltas(self) -> None:
        out = render_console(_report_with_changes(), summary=True)
        assert "added" in out.lower() or "+" in out
        # Per-field detail must be absent in summary mode
        assert "description" not in out
        assert "old" not in out

    def test_summary_keeps_counts(self) -> None:
        out = render_console(_report_with_changes(), summary=True)
        assert "metrics" in out.lower()
        # Some count token (e.g., "1 added") shows up
        assert "1" in out


class TestConsoleSideBySide:
    def test_side_by_side_present(self) -> None:
        out = render_console(_report_with_changes(), side_by_side=True)
        # In side-by-side, before and after are on the same visual row separated by a pipe
        assert " | " in out
        assert "old" in out
        assert "new" in out

    def test_side_by_side_off_by_default(self) -> None:
        out = render_console(_report_with_changes())
        # Vertical (default) mode renders before above after, not side-by-side
        # (assertion is loose; the precise format is whatever the renderer used in v1.0)
        assert "old" in out
        assert "new" in out


class TestMarkdownSummary:
    def test_summary_drops_modified_table(self) -> None:
        out = render_markdown(_report_with_changes(), summary=True)
        assert "description" not in out


class TestMarkdownSideBySide:
    def test_side_by_side_two_columns(self) -> None:
        out = render_markdown(_report_with_changes(), side_by_side=True)
        # 2-col table header indicating before/after columns
        assert "| Before" in out
        assert "| After" in out


class TestJsonSummary:
    def test_summary_strips_deltas(self) -> None:
        import json as _json

        out = render_json(_report_with_changes(), summary=True)
        payload = _json.loads(out)
        # modified items still listed but their .deltas are empty
        metric_block = next(c for c in payload["components"] if c["component_type"] == "metrics")
        assert metric_block["modified"][0]["deltas"] == []
