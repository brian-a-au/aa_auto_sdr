"""Pure post-compare filters for diff renderers — no I/O."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers._filters import filter_for_render
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def _report() -> DiffReport:
    return DiffReport(
        a_rsid="RS1",
        b_rsid="RS1",
        a_captured_at="2026-04-25T10:00:00+00:00",
        b_captured_at="2026-04-26T10:00:00+00:00",
        a_tool_version="1.2.0",
        b_tool_version="1.2.0",
        components=[
            ComponentDiff(
                component_type="metrics",
                added=[AddedRemovedItem(id=f"m{i}", name=f"Metric {i}") for i in range(5)],
                modified=[
                    ModifiedItem(id="mx", name="X", deltas=[FieldDelta(field="name", before="a", after="b")]),
                ],
                unchanged_count=10,
            ),
            ComponentDiff(component_type="dimensions", added=[], removed=[], modified=[], unchanged_count=20),
            ComponentDiff(
                component_type="segments",
                removed=[AddedRemovedItem(id="s1", name="Old Segment")],
                unchanged_count=5,
            ),
        ],
    )


class TestChangesOnly:
    def test_drops_components_with_no_changes(self) -> None:
        out = filter_for_render(_report(), changes_only=True)
        types = [c.component_type for c in out.components]
        assert "metrics" in types
        assert "segments" in types
        assert "dimensions" not in types  # no changes → dropped

    def test_default_keeps_all(self) -> None:
        out = filter_for_render(_report())
        assert len(out.components) == 3


class TestShowOnly:
    def test_restricts_to_named_types(self) -> None:
        out = filter_for_render(_report(), show_only=frozenset({"metrics"}))
        assert len(out.components) == 1
        assert out.components[0].component_type == "metrics"

    def test_unknown_type_returns_empty(self) -> None:
        out = filter_for_render(_report(), show_only=frozenset({"nonexistent"}))
        assert out.components == []


class TestMaxIssues:
    def test_caps_added_list(self) -> None:
        out = filter_for_render(_report(), max_issues=2)
        metrics = next(c for c in out.components if c.component_type == "metrics")
        assert len(metrics.added) == 2
        # Modified list also capped at 2 (originally has 1, so unchanged)
        assert len(metrics.modified) == 1

    def test_zero_max_issues_drops_all_items(self) -> None:
        out = filter_for_render(_report(), max_issues=0)
        for c in out.components:
            assert c.added == []
            assert c.removed == []
            assert c.modified == []


class TestCombined:
    def test_changes_only_plus_show_only(self) -> None:
        out = filter_for_render(
            _report(),
            changes_only=True,
            show_only=frozenset({"metrics", "dimensions"}),
        )
        # show_only keeps metrics + dimensions; changes_only drops dimensions (empty)
        assert [c.component_type for c in out.components] == ["metrics"]

    def test_all_three_combined(self) -> None:
        out = filter_for_render(
            _report(),
            changes_only=True,
            show_only=frozenset({"metrics", "segments"}),
            max_issues=1,
        )
        types = [c.component_type for c in out.components]
        assert types == ["metrics", "segments"]
        metrics = next(c for c in out.components if c.component_type == "metrics")
        assert len(metrics.added) == 1


def test_does_not_mutate_input() -> None:
    report = _report()
    metrics_before = report.components[0].added[:]
    filter_for_render(report, max_issues=1)
    # Input list unchanged
    assert report.components[0].added == metrics_before
