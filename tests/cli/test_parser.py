"""Argparse surface for v0.1: positional RSID, profile, format, output-dir, profile-add, show-config."""

import pytest

from aa_auto_sdr.cli.parser import build_parser


def test_positional_rsid() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.rsid == "demo.prod"


def test_format_default_is_excel() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.format == "excel"


def test_format_accepts_aliases() -> None:
    p = build_parser()
    for fmt in ("excel", "json", "all", "data", "ci", "reports"):
        ns = p.parse_args(["demo.prod", "--format", fmt])
        assert ns.format == fmt


def test_format_rejects_unknown() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["demo.prod", "--format", "nonsense"])


def test_output_dir_default_is_dot() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert str(ns.output_dir) == "."


def test_profile_add_is_action() -> None:
    p = build_parser()
    ns = p.parse_args(["--profile-add", "prod"])
    assert ns.profile_add == "prod"


def test_profile_add_is_mutually_exclusive_with_rsid() -> None:
    """v0.1 defines --profile-add as a standalone action — RSID not required."""
    p = build_parser()
    ns = p.parse_args(["--profile-add", "prod"])
    assert ns.rsid is None


def test_show_config_is_action() -> None:
    p = build_parser()
    ns = p.parse_args(["--show-config"])
    assert ns.show_config is True
    assert ns.rsid is None


def test_profile_flag() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod", "--profile", "prod"])
    assert ns.profile == "prod"
