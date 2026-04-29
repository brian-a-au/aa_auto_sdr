"""argparse plumbing for v1.3.0 logging + color-theme flags."""

from __future__ import annotations

import pytest

from aa_auto_sdr.cli.parser import build_parser


def test_log_level_default_is_none() -> None:
    """Default is None so setup_logging() can apply env-var fallback."""
    ns = build_parser().parse_args([])
    assert ns.log_level is None


def test_log_level_choices_enforced() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--log-level", "LOUD"])


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_log_level_accepts_valid(level: str) -> None:
    ns = build_parser().parse_args(["--log-level", level])
    assert ns.log_level == level


def test_log_format_default_is_text() -> None:
    ns = build_parser().parse_args([])
    assert ns.log_format == "text"


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_log_format_accepts_valid(fmt: str) -> None:
    ns = build_parser().parse_args(["--log-format", fmt])
    assert ns.log_format == fmt


def test_log_format_choices_enforced() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--log-format", "xml"])


def test_quiet_default_false() -> None:
    ns = build_parser().parse_args([])
    assert ns.quiet is False


def test_quiet_long_form() -> None:
    ns = build_parser().parse_args(["--quiet"])
    assert ns.quiet is True


def test_quiet_short_form() -> None:
    ns = build_parser().parse_args(["-q"])
    assert ns.quiet is True


def test_color_theme_default() -> None:
    ns = build_parser().parse_args([])
    assert ns.color_theme == "default"


@pytest.mark.parametrize("theme", ["default", "accessible"])
def test_color_theme_accepts_valid(theme: str) -> None:
    ns = build_parser().parse_args(["--color-theme", theme])
    assert ns.color_theme == theme


def test_color_theme_choices_enforced() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--color-theme", "neon"])
