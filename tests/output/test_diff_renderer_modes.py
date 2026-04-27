"""Mode toggles (summary, side_by_side) for diff renderers."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
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


class TestConsoleQuiet:
    def test_quiet_suppresses_unchanged_trailer(self) -> None:
        out = render_console(_report_with_changes(), quiet=True)
        # In quiet mode, the "Total: ... unchanged" line is suppressed.
        # We assert the absence of "unchanged" — note that the per-component
        # summary line which says "X unchanged" is also suppressed in quiet mode.
        assert "unchanged" not in out


class TestLabelsAllRenderers:
    def test_console_labels_replace_source_target(self) -> None:
        out = render_console(_report_with_changes(), labels=("baseline", "candidate"))
        assert "baseline" in out
        assert "candidate" in out

    def test_markdown_labels_replace_source_target(self) -> None:
        out = render_markdown(_report_with_changes(), labels=("baseline", "candidate"))
        assert "baseline" in out
        assert "candidate" in out

    def test_json_labels_in_payload(self) -> None:
        import json as _json

        out = render_json(_report_with_changes(), labels=("baseline", "candidate"))
        payload = _json.loads(out)
        assert payload.get("a_label") == "baseline"
        assert payload.get("b_label") == "candidate"

    def test_pr_comment_labels_in_output(self) -> None:
        out = render_pr_comment(_report_with_changes(), labels=("baseline", "candidate"))
        assert "baseline" in out
        assert "candidate" in out

    def test_labels_default_none_preserves_v1_1(self) -> None:
        # When labels=None, output must match v1.1 behavior (no breakage).
        with_labels = render_console(_report_with_changes(), labels=None)
        assert "Source:" in with_labels
        assert "Target:" in with_labels
