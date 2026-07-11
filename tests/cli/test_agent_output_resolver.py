"""Tests for per-command-family stdout resolver (spec §4.2)."""

from __future__ import annotations

import argparse

from aa_auto_sdr.cli.agent_output import (
    DIFF_STDOUT_FORMATS,
    DISCOVERY_STDOUT_FORMATS,
    STATS_STDOUT_FORMATS,
    is_stdout_path,
    resolve_agent_output_path,
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
    # Case-sensitive — only lowercase Unix conventions count
    assert is_stdout_path("STDOUT") is False
    assert is_stdout_path("Stdout") is False


def test_capability_sets():
    assert frozenset({"json"}) == DIFF_STDOUT_FORMATS
    assert frozenset({"json", "csv"}) == DISCOVERY_STDOUT_FORMATS
    assert frozenset({"json"}) == STATS_STDOUT_FORMATS


def test_resolve_returns_unchanged_when_agent_mode_off():
    ns = _ns(agent_mode=False, output="-")
    assert resolve_agent_output_path(ns, argv=[], output_format="json", stdout_formats=DIFF_STDOUT_FORMATS) == "-"


def test_resolve_returns_unchanged_when_explicit_output():
    """Explicit --output on argv wins even if format is not stdout-capable."""
    argv = ["--output", "/tmp/out.json"]
    ns = _ns(agent_mode=True, output="/tmp/out.json")
    assert (
        resolve_agent_output_path(ns, argv=argv, output_format="excel", stdout_formats=frozenset()) == "/tmp/out.json"
    )


def test_resolve_returns_unchanged_when_explicit_output_equals_form():
    """`--output=value` form also detected as explicit."""
    argv = ["--output=/tmp/out.json"]
    ns = _ns(agent_mode=True, output="/tmp/out.json")
    assert (
        resolve_agent_output_path(ns, argv=argv, output_format="excel", stdout_formats=frozenset()) == "/tmp/out.json"
    )


def test_resolve_returns_unchanged_when_format_is_stdout_capable():
    argv = ["--agent-mode"]
    ns = _ns(agent_mode=True, output="-")
    assert resolve_agent_output_path(ns, argv=argv, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS) == "-"


def test_resolve_suppresses_when_format_not_stdout_capable():
    """Generate's empty stdout_formats branch — agent-mode default `--output -` is suppressed."""
    argv = ["--agent-mode"]
    ns = _ns(agent_mode=True, output="-")
    assert resolve_agent_output_path(ns, argv=argv, output_format="excel", stdout_formats=frozenset()) is None


def test_resolve_suppresses_when_format_not_in_set():
    """Diff with markdown format is not stdout-capable under contract."""
    argv = ["--agent-mode", "--format", "markdown"]
    ns = _ns(agent_mode=True, output="-", format="markdown")
    assert (
        resolve_agent_output_path(ns, argv=argv, output_format="markdown", stdout_formats=DIFF_STDOUT_FORMATS) is None
    )


def test_argv_none_falls_back_to_sys_argv(monkeypatch):
    """Back-compat: argv=None falls back to sys.argv[1:] for callers that don't thread argv."""
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--output", "/tmp/out.json"])
    ns = _ns(agent_mode=True, output="/tmp/out.json")
    # argv=None (default) should still detect --output as explicit
    assert resolve_agent_output_path(ns, output_format="excel", stdout_formats=frozenset()) == "/tmp/out.json"
