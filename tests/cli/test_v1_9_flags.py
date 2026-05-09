"""v1.9.0 CLI flag parsing — see spec §3.8 + §4.4 + §4.5."""

from __future__ import annotations

import argparse

import pytest

from aa_auto_sdr.cli.parser import build_parser


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return build_parser()


# Shipped flags ------------------------------------------------------------


def test_extended_fields_default_false(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--diff", "snap_a", "snap_b"])
    assert args.extended_fields is False


def test_extended_fields_set_true(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--diff", "snap_a", "snap_b", "--extended-fields"])
    assert args.extended_fields is True


def test_name_match_default_insensitive(parser: argparse.ArgumentParser) -> None:
    """Default preserves pre-v1.9.0 case-insensitive behavior."""
    args = parser.parse_args(["rs1"])
    assert args.name_match == "insensitive"


def test_name_match_accepts_exact(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1", "--name-match", "exact"])
    assert args.name_match == "exact"


def test_name_match_accepts_insensitive(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1", "--name-match", "insensitive"])
    assert args.name_match == "insensitive"


def test_name_match_accepts_fuzzy(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1", "--name-match", "fuzzy"])
    assert args.name_match == "fuzzy"


def test_name_match_rejects_invalid_strategy(parser: argparse.ArgumentParser) -> None:
    with pytest.raises(SystemExit):
        parser.parse_args(["rs1", "--name-match", "bogus"])


def test_audit_naming_default_false(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1"])
    assert args.audit_naming is False


def test_audit_naming_set_true(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1", "--audit-naming"])
    assert args.audit_naming is True


def test_flag_stale_default_false(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1"])
    assert args.flag_stale is False


def test_flag_stale_set_true(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["rs1", "--flag-stale"])
    assert args.flag_stale is True


def test_audit_and_flag_stale_independent(parser: argparse.ArgumentParser) -> None:
    """Both can be set together; either alone; neither (default)."""
    args = parser.parse_args(["rs1", "--audit-naming", "--flag-stale"])
    assert args.audit_naming is True
    assert args.flag_stale is True


# Dropped flags (must be rejected) ----------------------------------------


def test_no_component_types_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.9.0 dropped --no-component-types per spec §2.2."""
    with pytest.raises(SystemExit):
        parser.parse_args(["rs1", "--no-component-types"])


def test_lock_stale_threshold_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.9.0 dropped --lock-stale-threshold per spec §2.2."""
    with pytest.raises(SystemExit):
        parser.parse_args(["rs1", "--lock-stale-threshold", "60"])


def test_include_names_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.9.0 dropped --include-names per spec §2.2."""
    with pytest.raises(SystemExit):
        parser.parse_args(["rs1", "--include-names"])


def test_include_metadata_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.9.0 dropped --include-metadata per spec §2.2."""
    with pytest.raises(SystemExit):
        parser.parse_args(["rs1", "--include-metadata"])
