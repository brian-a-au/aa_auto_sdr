"""Tests for the pr-comment diff renderer (GFM compact, GitHub PR target)."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers.pr_comment import (
    LENGTH_CAP,
    render_pr_comment,
)
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def _empty_report(rsid: str = "RS1", mismatch: bool = False) -> DiffReport:
    return DiffReport(
        a_rsid=rsid,
        b_rsid="OTHER" if mismatch else rsid,
        a_captured_at="2026-04-25T10:00:00+00:00",
        b_captured_at="2026-04-26T10:00:00+00:00",
        a_tool_version="1.1.0",
        b_tool_version="1.1.0",
        rsid_mismatch=mismatch,
    )


class TestPrComment:
    def test_empty_diff_renders_short(self) -> None:
        out = render_pr_comment(_empty_report())
        assert "SDR Diff" in out
        assert "RS1" in out
        assert len(out) < 1000

    def test_rsid_mismatch_warning(self) -> None:
        out = render_pr_comment(_empty_report(mismatch=True))
        assert "RSID mismatch" in out

    def test_added_collapsed_section(self) -> None:
        report = DiffReport(
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
                )
            ],
        )
        out = render_pr_comment(report)
        assert "<details>" in out
        assert "Added" in out
        assert "m2" in out

    def test_long_string_delta_truncated(self) -> None:
        long_value = "x" * 500
        report = DiffReport(
            a_rsid="RS1",
            b_rsid="RS1",
            a_captured_at="2026-04-25T10:00:00+00:00",
            b_captured_at="2026-04-26T10:00:00+00:00",
            a_tool_version="1.1.0",
            b_tool_version="1.1.0",
            components=[
                ComponentDiff(
                    component_type="metrics",
                    modified=[
                        ModifiedItem(
                            id="m1",
                            name="X",
                            deltas=[FieldDelta(field="description", before=long_value, after="short")],
                        )
                    ],
                )
            ],
        )
        out = render_pr_comment(report)
        assert "…" in out  # inline truncation marker

    def test_overall_truncation_banner_when_huge(self) -> None:
        massive = ComponentDiff(
            component_type="metrics",
            modified=[
                ModifiedItem(
                    id=f"m{i}",
                    name=f"M{i}",
                    deltas=[FieldDelta(field="name", before=f"old{i}", after=f"new{i}")],
                )
                for i in range(2000)
            ],
        )
        report = DiffReport(
            a_rsid="RS1",
            b_rsid="RS1",
            a_captured_at="2026-04-25T10:00:00+00:00",
            b_captured_at="2026-04-26T10:00:00+00:00",
            a_tool_version="1.1.0",
            b_tool_version="1.1.0",
            components=[massive],
        )
        out = render_pr_comment(report)
        assert len(out) <= LENGTH_CAP
        assert "truncated" in out

    def test_summary_mode_drops_detail(self) -> None:
        report = DiffReport(
            a_rsid="RS1",
            b_rsid="RS1",
            a_captured_at="2026-04-25T10:00:00+00:00",
            b_captured_at="2026-04-26T10:00:00+00:00",
            a_tool_version="1.1.0",
            b_tool_version="1.1.0",
            components=[
                ComponentDiff(
                    component_type="metrics",
                    modified=[
                        ModifiedItem(
                            id="m1",
                            name="X",
                            deltas=[FieldDelta(field="name", before="a", after="b")],
                        )
                    ],
                )
            ],
        )
        out = render_pr_comment(report, summary=True)
        # Summary keeps counts, drops field-by-field detail
        assert "1" in out
        assert "metrics" in out
        # Field-level detail is suppressed
        assert "name" not in out.lower() or out.lower().count("name") < 3
