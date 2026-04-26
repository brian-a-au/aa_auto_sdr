"""output/diff_renderers/markdown.py — GFM diff renderer."""

from __future__ import annotations

from dataclasses import replace

from aa_auto_sdr.output.diff_renderers.markdown import render_markdown
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def _empty_report(rsid: str = "demo.prod") -> DiffReport:
    return DiffReport(
        a_rsid=rsid,
        b_rsid=rsid,
        a_captured_at="2026-04-20T10:00:00+00:00",
        b_captured_at="2026-04-26T17:29:01+00:00",
        a_tool_version="0.5.0",
        b_tool_version="0.7.0",
        report_suite_deltas=[],
        components=[
            ComponentDiff(component_type=ct, unchanged_count=0)
            for ct in (
                "dimensions",
                "metrics",
                "segments",
                "calculated_metrics",
                "virtual_report_suites",
                "classifications",
            )
        ],
    )


def test_render_markdown_returns_string() -> None:
    assert isinstance(render_markdown(_empty_report()), str)


def test_render_markdown_includes_h1_title() -> None:
    out = render_markdown(_empty_report())
    assert out.startswith("# SDR Diff")


def test_render_markdown_includes_source_target_metadata() -> None:
    out = render_markdown(_empty_report())
    assert "demo.prod" in out
    assert "2026-04-20T10:00:00+00:00" in out
    assert "2026-04-26T17:29:01+00:00" in out


def test_render_markdown_omits_empty_component_sections() -> None:
    """Empty added/removed/modified lists shouldn't produce a section."""
    out = render_markdown(_empty_report())
    assert "## Dimensions" not in out
    assert "## Metrics" not in out


def test_render_markdown_added_table() -> None:
    rep = _empty_report()
    rep_components = list(rep.components)
    rep_components[0] = ComponentDiff(
        component_type="dimensions",
        added=[AddedRemovedItem(id="evar2", name="Plan")],
        unchanged_count=0,
    )
    rep2 = replace(rep, components=rep_components)
    out = render_markdown(rep2)
    assert "## Dimensions" in out
    assert "### Added" in out
    assert "| evar2 | Plan |" in out


def test_render_markdown_modified_table_includes_field_columns() -> None:
    rep = _empty_report()
    rep_components = list(rep.components)
    rep_components[0] = ComponentDiff(
        component_type="dimensions",
        modified=[
            ModifiedItem(
                id="evar1",
                name="User ID",
                deltas=[FieldDelta(field="type", before="string", after="enum")],
            ),
        ],
        unchanged_count=0,
    )
    rep2 = replace(rep, components=rep_components)
    out = render_markdown(rep2)
    assert "### Modified" in out
    assert "| Field | Before | After |" in out
    assert "type" in out
    assert "string" in out
    assert "enum" in out


def test_render_markdown_escapes_pipes_in_values() -> None:
    rep = _empty_report()
    rep_components = list(rep.components)
    rep_components[0] = ComponentDiff(
        component_type="dimensions",
        modified=[
            ModifiedItem(
                id="evar1",
                name="Pipe|Name",
                deltas=[FieldDelta(field="x", before="a|b", after="c")],
            ),
        ],
        unchanged_count=0,
    )
    rep2 = replace(rep, components=rep_components)
    out = render_markdown(rep2)
    assert "Pipe\\|Name" in out
    assert "a\\|b" in out
