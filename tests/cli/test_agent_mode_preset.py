"""Tests for `--agent-mode` preset application (spec §4.1)."""

from __future__ import annotations

import pytest

from aa_auto_sdr.cli.main import run as cli_run  # noqa: F401  (import smoke)
from aa_auto_sdr.cli.parser import build_parser


def _parse(argv: list[str]):
    """Mimic cli.main.run's parse-then-apply sequence."""
    from aa_auto_sdr.cli.parser import _apply_agent_mode_defaults, _configured_long_options

    parser = build_parser()
    ns = parser.parse_args(argv)
    _apply_agent_mode_defaults(ns, argv, known_long_options=_configured_long_options(parser))
    return ns


def test_agent_mode_off_leaves_defaults_unchanged():
    ns = _parse(["--list-reportsuites"])
    assert ns.agent_mode is False
    # No assertion on format/output/log_format — argparse defaults govern.


def test_agent_mode_alone_applies_three_defaults():
    ns = _parse(["--agent-mode", "--list-reportsuites"])
    assert ns.agent_mode is True
    assert ns.format == "json"
    assert ns.output == "-"
    assert ns.log_format == "json"


def test_explicit_format_wins_over_preset():
    ns = _parse(["--agent-mode", "--list-reportsuites", "--format", "csv"])
    assert ns.format == "csv"
    assert ns.output == "-"  # output still defaults
    assert ns.log_format == "json"


def test_explicit_format_equals_form_wins_over_preset():
    ns = _parse(["--agent-mode", "--list-reportsuites", "--format=csv"])
    assert ns.format == "csv"


def test_explicit_output_wins_over_preset():
    ns = _parse(["--agent-mode", "--list-reportsuites", "--output", "/tmp/out.json"])
    assert ns.output == "/tmp/out.json"
    assert ns.format == "json"
    assert ns.log_format == "json"


def test_explicit_log_format_wins_over_preset():
    ns = _parse(["--agent-mode", "--list-reportsuites", "--log-format", "text"])
    assert ns.log_format == "text"
    assert ns.format == "json"
    assert ns.output == "-"


def test_all_three_explicit_overrides():
    ns = _parse(
        ["--agent-mode", "--list-reportsuites", "--format", "csv", "--output", "/tmp/x.csv", "--log-format", "text"]
    )
    assert ns.format == "csv"
    assert ns.output == "/tmp/x.csv"
    assert ns.log_format == "text"


def test_agent_mode_flag_appears_in_help():
    parser = build_parser()
    help_text = parser.format_help()
    assert "--agent-mode" in help_text
    assert "json" in help_text  # preset's format default


def test_argparse_abbreviation_disabled():
    """Codex review (P2): abbreviated long options bypass the explicit-option
    detector and let the agent-mode preset overwrite the user's choice. Parser
    must reject abbreviations so the contract holds."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        # --forma is an abbreviation of --format; must be rejected.
        parser.parse_args(["--forma", "csv", "--list-reportsuites"])


def test_abbreviation_does_not_let_preset_override_user_choice():
    """Regression guard for the Codex finding: even when an abbreviation is
    typo'd, the agent-mode preset must never silently overwrite the user's
    explicit choice. With ``allow_abbrev=False`` the parser exits before the
    preset runs, which is the correct outcome."""
    with pytest.raises(SystemExit):
        _parse(["--agent-mode", "--forma", "csv", "--list-reportsuites"])
