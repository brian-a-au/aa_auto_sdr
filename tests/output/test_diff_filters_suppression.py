"""Filter pre-flight behavior under suppressed sections — spec §4.8."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers._filters import filter_for_render
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
)


def _report() -> DiffReport:
    return DiffReport(
        a_rsid="rs1",
        b_rsid="rs1",
        a_captured_at="2026-05-01T00:00:00+00:00",
        b_captured_at="2026-05-08T00:00:00+00:00",
        a_tool_version="1.7.0",
        b_tool_version="1.7.1",
        components=[
            ComponentDiff(component_type="dimensions"),  # empty, healthy
            ComponentDiff(
                component_type="virtual_report_suites",
                suppressed=True,
                suppression_reason="fetch degraded",
            ),
            ComponentDiff(
                component_type="classifications",
                added=[AddedRemovedItem(id="c1", name="C1")],
            ),
        ],
    )


def test_changes_only_keeps_suppressed_sections() -> None:
    """A suppressed section IS a kind of change-signal (fetch quality differed)."""
    filtered = filter_for_render(_report(), changes_only=True)
    component_types = {c.component_type for c in filtered.components}
    assert "virtual_report_suites" in component_types  # suppressed survives
    assert "classifications" in component_types  # has changes
    assert "dimensions" not in component_types  # empty + healthy → filtered out


def test_show_only_filters_by_component_type_unchanged() -> None:
    filtered = filter_for_render(_report(), show_only=frozenset({"virtual_report_suites"}))
    assert len(filtered.components) == 1
    assert filtered.components[0].component_type == "virtual_report_suites"
    assert filtered.components[0].suppressed is True


def test_max_issues_does_not_count_suppressed_sections() -> None:
    """Suppressed sections aren't add/remove/modify; they shouldn't count toward N."""
    filtered = filter_for_render(_report(), max_issues=1)
    cls = next(c for c in filtered.components if c.component_type == "classifications")
    assert len(cls.added) == 1
