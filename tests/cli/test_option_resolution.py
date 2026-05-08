"""Tests for explicit-long-option detection (spec §4.4)."""

from __future__ import annotations

import pytest

from aa_auto_sdr.cli.option_resolution import explicit_long_option_dests


@pytest.mark.parametrize(
    ("argv", "tracked", "known", "expected"),
    [
        # No tracked options present
        (["--list-reportsuites"], {"--format", "--output"}, {"--list-reportsuites", "--format", "--output"}, set()),
        # Bare-token form
        (["--format", "json"], {"--format"}, {"--format"}, {"format"}),
        # --option=value form
        (["--format=json"], {"--format"}, {"--format"}, {"format"}),
        # Multiple tracked options
        (
            ["--format", "json", "--output", "-"],
            {"--format", "--output"},
            {"--format", "--output"},
            {"format", "output"},
        ),
        # Hyphen-to-underscore conversion in dest
        (["--log-format", "json"], {"--log-format"}, {"--log-format"}, {"log_format"}),
        # Unknown long option ignored
        (["--unknown", "x"], {"--format"}, {"--format"}, set()),
        # Tracked option absent
        (
            ["--list-reportsuites", "--profile", "prod"],
            {"--format"},
            {"--format", "--profile", "--list-reportsuites"},
            set(),
        ),
    ],
)
def test_explicit_long_option_dests(argv, tracked, known, expected):
    result = explicit_long_option_dests(
        argv,
        tracked_options=frozenset(tracked),
        known_long_options=frozenset(known),
    )
    assert result == expected


def test_none_argv_uses_sys_argv(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", ["prog", "--format", "json"])
    result = explicit_long_option_dests(
        None,
        tracked_options=frozenset({"--format"}),
        known_long_options=frozenset({"--format"}),
    )
    assert result == {"format"}
