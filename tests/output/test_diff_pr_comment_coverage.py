"""Targeted coverage for the pr-comment diff renderer.

Covers the removed-components <details> block, which the existing suite leaves
unexercised."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.models import AddedRemovedItem, ComponentDiff, DiffReport


def _report_with_removed() -> DiffReport:
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
                removed=[AddedRemovedItem(id="m9", name="Retired Metric")],
            )
        ],
    )


def test_removed_components_block_rendered() -> None:
    out = render_pr_comment(_report_with_removed())
    assert "Removed components" in out
    assert "m9" in out
    assert "Retired Metric" in out
