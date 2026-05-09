"""Diff renderers branch on ComponentDiff.suppressed — spec §4.8."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
)


def _report_with_suppressed_vrs() -> DiffReport:
    return DiffReport(
        a_rsid="rs1",
        b_rsid="rs1",
        a_captured_at="2026-05-01T00:00:00+00:00",
        b_captured_at="2026-05-08T00:00:00+00:00",
        a_tool_version="1.7.0",
        b_tool_version="1.7.1",
        components=[
            ComponentDiff(component_type="dimensions"),
            ComponentDiff(component_type="metrics"),
            ComponentDiff(component_type="segments"),
            ComponentDiff(component_type="calculated_metrics"),
            ComponentDiff(
                component_type="virtual_report_suites",
                suppressed=True,
                suppression_reason="fetch partial (expansion_level=minimal)",
            ),
            ComponentDiff(
                component_type="classifications",
                added=[AddedRemovedItem(id="c1", name="C1")],
            ),
        ],
    )


def test_console_emits_suppressed_annotation() -> None:
    out = render_console(_report_with_suppressed_vrs())
    assert "Virtual report suites" in out
    assert "fetch partial (expansion_level=minimal)" in out
    assert "diff suppressed" in out
    # Healthy classifications still rendered normally
    assert "Classifications" in out
    # Per-side counts deliberately NOT in the message — see spec §8 closed open question.
    assert "components on left" not in out


def test_markdown_emits_suppressed_blockquote() -> None:
    out = render_markdown(_report_with_suppressed_vrs())
    assert "> ⚠ Virtual Report Suites" in out
    assert "fetch partial (expansion_level=minimal)" in out
    assert "diff suppressed" in out


def test_json_carries_suppressed_fields() -> None:
    """asdict serializes new ComponentDiff fields automatically."""
    import json as _json

    raw = render_json(_report_with_suppressed_vrs())
    data = _json.loads(raw)
    vrs = next(c for c in data["components"] if c["component_type"] == "virtual_report_suites")
    assert vrs["suppressed"] is True
    assert vrs["suppression_reason"] == "fetch partial (expansion_level=minimal)"
    cls = next(c for c in data["components"] if c["component_type"] == "classifications")
    assert cls["suppressed"] is False
    assert cls["suppression_reason"] is None


def test_pr_comment_emits_suppressed_annotation() -> None:
    out = render_pr_comment(_report_with_suppressed_vrs())
    assert "⚠" in out
    assert "Virtual Report Suites" in out
    assert "fetch partial (expansion_level=minimal)" in out
    assert "diff suppressed" in out


def test_renderers_skip_per_row_detail_when_suppressed() -> None:
    """Suppressed sections should NOT emit per-row tables/lists."""
    report = DiffReport(
        a_rsid="rs1",
        b_rsid="rs1",
        a_captured_at="2026-05-01T00:00:00+00:00",
        b_captured_at="2026-05-08T00:00:00+00:00",
        a_tool_version="1.7.0",
        b_tool_version="1.7.1",
        components=[
            ComponentDiff(
                component_type="virtual_report_suites",
                added=[AddedRemovedItem(id="v1", name="should-not-appear")],
                suppressed=True,
                suppression_reason="fetch degraded",
            ),
        ],
    )
    md = render_markdown(report)
    console = render_console(report)
    pr = render_pr_comment(report)
    assert "should-not-appear" not in md
    assert "should-not-appear" not in console
    assert "should-not-appear" not in pr
