"""Sentinel test: BANNER_WIDTH is the source of truth for summary banner width."""

from aa_auto_sdr.core.constants import BANNER_WIDTH


def test_banner_width_is_60() -> None:
    assert BANNER_WIDTH == 60
