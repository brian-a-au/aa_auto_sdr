"""parse_duration() — Nh|Nd|Nw grammar shared by retention and trending."""

from __future__ import annotations

from datetime import timedelta

import pytest

from aa_auto_sdr.snapshot._duration import parse_duration


class TestParseDurationHappyPath:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("1h", timedelta(hours=1)),
            ("12h", timedelta(hours=12)),
            ("1d", timedelta(hours=24)),
            ("30d", timedelta(days=30)),
            ("1w", timedelta(days=7)),
            ("4w", timedelta(days=28)),
        ],
    )
    def test_valid_durations(self, spec: str, expected: timedelta) -> None:
        assert parse_duration(spec) == expected


class TestParseDurationErrors:
    @pytest.mark.parametrize(
        "spec",
        [
            "30",  # bare int — must have unit
            "30m",  # months not supported
            "1y",  # years not supported
            "30days",  # unit must be single char
            "",  # empty
            "d30",  # wrong order
            "30 d",  # space
            "-5d",  # negative
            "garbage",  # nonsense
        ],
    )
    def test_invalid_durations_raise_valueerror(self, spec: str) -> None:
        with pytest.raises(ValueError, match="invalid duration"):
            parse_duration(spec)
