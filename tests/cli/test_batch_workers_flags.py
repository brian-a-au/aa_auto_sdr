"""--workers, --fail-fast, and cache flags — see spec §3.5."""

from __future__ import annotations

import argparse

import pytest

from aa_auto_sdr.cli.parser import build_parser


@pytest.fixture
def parser() -> argparse.ArgumentParser:
    return build_parser()


def test_workers_flag_default_is_one(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1", "rs2"])
    assert args.workers == 1


def test_workers_flag_accepts_positive_int(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1", "rs2", "--workers", "4"])
    assert args.workers == 4


def test_workers_flag_rejects_zero(parser: argparse.ArgumentParser) -> None:
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--workers", "0"])


def test_workers_flag_rejects_above_16(parser: argparse.ArgumentParser) -> None:
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--workers", "17"])


def test_fail_fast_flag_default_is_false(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1"])
    assert args.fail_fast is False


def test_fail_fast_flag_set(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1", "--fail-fast"])
    assert args.fail_fast is True


def test_enable_cache_default_off(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1"])
    assert args.enable_cache is False


def test_enable_cache_set(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1", "--enable-cache"])
    assert args.enable_cache is True


def test_clear_cache_default_off(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1"])
    assert args.clear_cache is False


def test_cache_ttl_default_3600(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1"])
    assert args.cache_ttl == 3600


def test_cache_ttl_accepts_int(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1", "--cache-ttl", "7200"])
    assert args.cache_ttl == 7200


def test_cache_ttl_rejects_zero(parser: argparse.ArgumentParser) -> None:
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--cache-ttl", "0"])


def test_cache_size_default_1000(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1"])
    assert args.cache_size == 1000


def test_cache_size_accepts_int(parser: argparse.ArgumentParser) -> None:
    args = parser.parse_args(["--batch", "rs1", "--cache-size", "500"])
    assert args.cache_size == 500


def test_cache_size_rejects_zero(parser: argparse.ArgumentParser) -> None:
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--cache-size", "0"])


def test_unknown_continue_on_error_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.8.0 dropped --continue-on-error per spec §3.5; ensure parser rejects it."""
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--continue-on-error"])


def test_unknown_shared_cache_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.8.0 dropped --shared-cache per spec §3.5."""
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--shared-cache"])


def test_unknown_use_cache_flag_rejected(parser: argparse.ArgumentParser) -> None:
    """v1.8.0 dropped --use-cache per spec §3.5."""
    with pytest.raises(SystemExit):
        parser.parse_args(["--batch", "rs1", "--use-cache"])
