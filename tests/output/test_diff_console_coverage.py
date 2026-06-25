"""Targeted coverage for the console diff renderer.

Covers the non-string branches of `_fmt_value` (None, dict/list JSON, scalar)
and the summary+quiet skip of unchanged-only components."""

from __future__ import annotations

import pytest

from aa_auto_sdr.output.diff_renderers import console
from aa_auto_sdr.output.diff_renderers.console import render_console
from aa_auto_sdr.snapshot.models import ComponentDiff, DiffReport

_COMPONENT_TYPES = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
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
        components=[ComponentDiff(component_type=ct, unchanged_count=10) for ct in _COMPONENT_TYPES],
    )


def test_fmt_value_none_renders_null() -> None:
    assert console._fmt_value(None) == "null"


def test_fmt_value_dict_and_list_render_compact_json() -> None:
    assert console._fmt_value({"b": 2, "a": 1}) == '{"a": 1, "b": 2}'
    assert console._fmt_value([1, 2]) == "[1, 2]"


def test_fmt_value_non_string_scalar_uses_str() -> None:
    assert console._fmt_value(42) == "42"


def test_render_console_summary_quiet_skips_unchanged_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    out = render_console(_empty_report(), summary=True, quiet=True)
    # Every component is unchanged-only → skipped, so no count lines emitted.
    assert "added" not in out
    assert "SDR DIFF" in out
