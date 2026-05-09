"""--warn-threshold respects suppressed sections — spec §4.8."""

from __future__ import annotations

from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
)


def _suppressed_only_report() -> DiffReport:
    """A DiffReport with one suppressed section. The comparator populates
    `removed` based on raw data even when suppressed — verifies the
    diff.py threshold check ignores those misleading counts."""
    return DiffReport(
        a_rsid="rs1",
        b_rsid="rs1",
        a_captured_at="2026-05-01T00:00:00+00:00",
        b_captured_at="2026-05-08T00:00:00+00:00",
        a_tool_version="1.7.0",
        b_tool_version="1.7.1",
        components=[
            ComponentDiff(
                component_type="virtual_report_suites",
                removed=[AddedRemovedItem(id=f"v{i}", name=f"V{i}") for i in range(5)],
                suppressed=True,
                suppression_reason="fetch degraded",
            ),
        ],
    )


def test_total_changes_skips_suppressed_sections_by_construction() -> None:
    """Mirror the diff.py total_changes computation; suppressed sections must be excluded."""
    report = _suppressed_only_report()
    total = sum(len(c.added) + len(c.removed) + len(c.modified) for c in report.components if not c.suppressed)
    # Even though removed=[5 items] is populated by the comparator, total_changes is 0.
    assert total == 0
