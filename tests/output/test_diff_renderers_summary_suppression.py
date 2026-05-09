"""Summary-mode + pr_comment top-line/table renderers must respect suppression.

Independent code review (PR #27) flagged that detailed-mode renderers
correctly skip suppressed sections (Task 9), but pr_comment's top-line +
breakdown table, markdown summary, and console summary emitted raw misleading
counts for suppressed sections (the comparator populates added/removed/modified
from raw data even when suppressed).

Review issues I-2 / I-3 from PR #27."""

from __future__ import annotations

import json as _json

from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
)


def _report_suppressed_with_misleading_counts() -> DiffReport:
    """A degraded VRS section: comparator populates removed=[5 items] from
    raw data, but suppressed=True signals 'don't trust these counts'."""
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
                removed=[AddedRemovedItem(id=f"v{i}", name=f"V{i}") for i in range(5)],
                suppressed=True,
                suppression_reason="fetch degraded",
            ),
            ComponentDiff(
                component_type="classifications",
                added=[AddedRemovedItem(id="c1", name="C1")],
            ),
        ],
    )


# ----- pr_comment.py: top-line + breakdown table ---------------------------


def test_pr_comment_top_line_excludes_suppressed_counts() -> None:
    """Top-line summary should show 1+/0-/0~ (only the classifications add),
    NOT 1+/5-/0~ (the misleading suppressed-VRS removed=5)."""
    out = render_pr_comment(_report_suppressed_with_misleading_counts())
    # Split at the breakdown section to isolate the top-line region.
    lines_before_breakdown = out.split("Component breakdown")[0]
    # The suppressed VRS removed=5 must NOT contribute to the visible totals.
    # "5" as a standalone count should not appear in the top-line region.
    # (The actual classification add is 1, so no other 5 appears in counts.)
    assert "Removed:** 5" not in lines_before_breakdown
    assert "Removed:** 0" in lines_before_breakdown
    # Suppression annotation should still appear somewhere in the output.
    assert "diff suppressed" in out


def test_pr_comment_breakdown_table_marks_suppressed_section() -> None:
    """The component breakdown table should NOT show raw counts for suppressed
    sections — replace with a suppressed marker instead of count integers."""
    out = render_pr_comment(_report_suppressed_with_misleading_counts())
    if "Component breakdown" in out:
        breakdown_region = out.split("Component breakdown", 1)[1]
        # End the region at the details close tag.
        breakdown_region = breakdown_region.split("</details>", 1)[0]
        # Find the VRS row in the breakdown.
        vrs_lines = [
            line
            for line in breakdown_region.splitlines()
            if "Virtual Report Suites" in line or "virtual_report_suites" in line
        ]
        assert vrs_lines, "VRS row should appear in the breakdown"
        for line in vrs_lines:
            # The misleading removed=5 count must not appear.
            assert "| 5 |" not in line, f"Suppressed VRS row leaked misleading removed=5 count: {line!r}"
            # The row should carry a suppression marker.
            assert "suppressed" in line.lower(), f"Suppressed VRS row missing suppression annotation: {line!r}"


# ----- markdown.py: summary mode ------------------------------------------


def test_markdown_summary_mode_excludes_suppressed_counts() -> None:
    out = render_markdown(_report_suppressed_with_misleading_counts(), summary=True)
    # The Summary section should not show the misleading 5-removed count for VRS.
    summary_region = out.split("Summary", 1)[1] if "Summary" in out else out
    vrs_lines = [line for line in summary_region.splitlines() if "Virtual Report Suites" in line]
    assert vrs_lines, "VRS row should appear in the markdown summary table"
    for line in vrs_lines:
        assert "| 5 |" not in line, f"Markdown summary leaked misleading removed=5: {line!r}"
        assert "suppressed" in line.lower(), f"Markdown summary VRS row missing suppression annotation: {line!r}"


def test_markdown_summary_quiet_mode_excludes_suppressed_counts() -> None:
    """quiet=True + summary=True: suppressed VRS should still be annotated,
    not show count 5 nor be silently dropped."""
    out = render_markdown(_report_suppressed_with_misleading_counts(), summary=True, quiet=True)
    # In quiet mode, the VRS section has counts (5 removed) and would normally
    # be included. With suppression it must show annotation, not the raw count.
    vrs_lines = [line for line in out.splitlines() if "Virtual Report Suites" in line]
    assert vrs_lines, "Suppressed VRS should still appear in quiet-summary mode"
    for line in vrs_lines:
        assert "| 5 |" not in line, f"Markdown quiet-summary leaked misleading removed=5: {line!r}"
        assert "suppressed" in line.lower(), f"Markdown quiet-summary VRS row missing annotation: {line!r}"


def test_markdown_summary_mode_carries_suppression_reason() -> None:
    """Symmetric with console/pr_comment: summary mode must surface why."""
    out = render_markdown(_report_suppressed_with_misleading_counts(), summary=True)
    assert "fetch degraded" in out  # The suppression_reason from the fixture


# ----- console.py: summary mode -------------------------------------------


def test_console_summary_mode_excludes_suppressed_counts() -> None:
    out = render_console(_report_suppressed_with_misleading_counts(), summary=True)
    # Find the VRS line — should be an annotation, not raw counts.
    vrs_lines = [line for line in out.splitlines() if "Virtual report suites" in line]
    assert vrs_lines, "VRS row should appear in the console summary"
    for line in vrs_lines:
        # Must not contain the raw "-5 removed" style count.
        assert "-5 removed" not in line, f"Console summary leaked misleading removed=5: {line!r}"
        assert "suppressed" in line.lower(), f"Console summary VRS row missing suppression annotation: {line!r}"


# ----- json.py: summary mode (no code change expected) --------------------


def test_json_summary_mode_carries_suppressed_fields() -> None:
    """JSON summary mode is opt-in (drops detail). Even so, the suppressed
    flag and reason should still be present per the spec."""
    from aa_auto_sdr.output.diff_renderers.json import render_json

    raw = render_json(_report_suppressed_with_misleading_counts(), summary=True)
    data = _json.loads(raw)
    vrs = next(c for c in data["components"] if c["component_type"] == "virtual_report_suites")
    assert vrs["suppressed"] is True
    assert vrs["suppression_reason"] == "fetch degraded"
