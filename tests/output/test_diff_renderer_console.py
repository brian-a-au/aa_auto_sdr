"""output/diff_renderers/console.py — banner-style console diff renderer."""

from __future__ import annotations

from dataclasses import replace

import pytest

from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def _empty_report() -> DiffReport:
    return DiffReport(
        a_rsid="demo.prod",
        b_rsid="demo.prod",
        a_captured_at="2026-04-20T10:00:00+00:00",
        b_captured_at="2026-04-26T17:29:01+00:00",
        a_tool_version="0.5.0",
        b_tool_version="0.7.0",
        report_suite_deltas=[],
        components=[
            ComponentDiff(component_type=ct, unchanged_count=10)
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


def test_render_console_returns_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    out = render_console(_empty_report())
    assert isinstance(out, str)


def test_render_console_no_color_when_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    out = render_console(_empty_report())
    assert "\033[" not in out


def test_render_console_includes_banner_and_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    out = render_console(_empty_report())
    assert "SDR DIFF" in out
    assert "=" * 60 in out  # BANNER_WIDTH


def test_render_console_includes_source_target_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    out = render_console(_empty_report())
    assert "Source: demo.prod @ 2026-04-20T10:00:00+00:00" in out
    assert "Target: demo.prod @ 2026-04-26T17:29:01+00:00" in out


def test_render_console_per_component_summary_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    out = render_console(_empty_report())
    # Six components, all 0/0/0/10 unchanged
    assert out.count(" 10 unchanged") == 6


def test_render_console_added_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    rep = _empty_report()
    comp = list(rep.components)
    comp[0] = ComponentDiff(
        component_type="dimensions",
        added=[AddedRemovedItem(id="evar99", name="Mobile")],
        unchanged_count=10,
    )
    rep2 = replace(rep, components=comp)
    out = render_console(rep2)
    assert "+ evar99 — Mobile" in out


def test_render_console_modified_with_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    rep = _empty_report()
    comp = list(rep.components)
    comp[0] = ComponentDiff(
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
    rep2 = replace(rep, components=comp)
    out = render_console(rep2)
    assert "~ evar1 — User ID" in out
    assert 'type: "string" → "enum"' in out


def test_render_console_rsid_mismatch_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    rep = replace(
        _empty_report(),
        b_rsid="demo.staging",
        rsid_mismatch=True,
    )
    out = render_console(rep)
    assert "RSID mismatch" in out
    assert "demo.prod" in out
    assert "demo.staging" in out


def test_render_console_uses_color_when_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    rep = _empty_report()
    comp = list(rep.components)
    comp[0] = ComponentDiff(
        component_type="dimensions",
        added=[AddedRemovedItem(id="evar99", name="Mobile")],
        unchanged_count=10,
    )
    rep2 = replace(rep, components=comp)
    out = render_console(rep2)
    assert "\033[" in out  # ANSI escape sequences present
