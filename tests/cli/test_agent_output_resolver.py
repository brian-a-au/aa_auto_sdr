"""Tests for per-command-family stdout resolver (spec §4.2)."""

from __future__ import annotations

import argparse

from aa_auto_sdr.cli.agent_output import (
    DIFF_STDOUT_FORMATS,
    DISCOVERY_STDOUT_FORMATS,
    STATS_STDOUT_FORMATS,
    is_stdout_path,
    resolve_agent_output_path,
    resolve_agent_quiet,
)


def _ns(**fields) -> argparse.Namespace:
    base = {
        "agent_mode": False,
        "output": None,
        "quiet": False,
        "run_summary_json": None,
    }
    base.update(fields)
    return argparse.Namespace(**base)


def test_is_stdout_path():
    assert is_stdout_path("-") is True
    assert is_stdout_path("stdout") is True
    assert is_stdout_path(None) is False
    assert is_stdout_path("/tmp/foo") is False


def test_capability_sets():
    assert frozenset({"json"}) == DIFF_STDOUT_FORMATS
    assert frozenset({"json", "csv"}) == DISCOVERY_STDOUT_FORMATS
    assert frozenset({"json"}) == STATS_STDOUT_FORMATS


def test_resolve_returns_unchanged_when_agent_mode_off():
    ns = _ns(agent_mode=False, output="-")
    assert resolve_agent_output_path(ns, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS) == "-"


def test_resolve_returns_unchanged_when_explicit_output(monkeypatch):
    """Explicit --output on argv wins even if format is not stdout-capable."""
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--output", "/tmp/out.json"])
    ns = _ns(agent_mode=True, output="/tmp/out.json")
    assert resolve_agent_output_path(ns, output_format="excel", stdout_formats=frozenset()) == "/tmp/out.json"


def test_resolve_returns_unchanged_when_format_is_stdout_capable(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--agent-mode"])
    ns = _ns(agent_mode=True, output="-")
    assert resolve_agent_output_path(ns, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS) == "-"


def test_resolve_suppresses_when_format_not_stdout_capable(monkeypatch):
    """Generate's empty stdout_formats branch — agent-mode default `--output -` is suppressed."""
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--agent-mode"])
    ns = _ns(agent_mode=True, output="-")
    assert resolve_agent_output_path(ns, output_format="excel", stdout_formats=frozenset()) is None


def test_resolve_suppresses_when_format_not_in_set(monkeypatch):
    """Diff with markdown format is not stdout-capable under contract."""
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--agent-mode", "--format", "markdown"])
    ns = _ns(agent_mode=True, output="-", format="markdown")
    assert resolve_agent_output_path(ns, output_format="markdown", stdout_formats=DIFF_STDOUT_FORMATS) is None


def test_quiet_explicit_wins(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--quiet"])
    ns = _ns(quiet=True, output="/tmp/out.xlsx")
    assert resolve_agent_quiet(ns, output_path="/tmp/out.xlsx") is True


def test_quiet_run_summary_stdout_implies_quiet(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--run-summary-json", "-"])
    ns = _ns(run_summary_json="-", output="/tmp/out.xlsx")
    assert resolve_agent_quiet(ns, output_path="/tmp/out.xlsx") is True


def test_quiet_stdout_output_implies_quiet(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--output", "-"])
    ns = _ns(output="-")
    assert resolve_agent_quiet(ns, output_path="-") is True


def test_quiet_file_output_does_not_imply_quiet(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--output", "/tmp/out.json"])
    ns = _ns(output="/tmp/out.json")
    assert resolve_agent_quiet(ns, output_path="/tmp/out.json") is False
