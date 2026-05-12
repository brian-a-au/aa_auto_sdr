"""Unit tests for the _calc_format_label decision tree. v1.16.0."""

from __future__ import annotations

from aa_auto_sdr.api import models
from aa_auto_sdr.output.writers.excel_template import _calc_format_label


def _cm(*, type_: str = "decimal", precision: int = 0) -> models.CalculatedMetric:
    return models.CalculatedMetric(
        id="cm_test",
        name="test",
        description=None,
        rsid="rs",
        owner_id=None,
        polarity="positive",
        precision=precision,
        type=type_,
        definition={},
    )


def test_percent_type_returns_percent() -> None:
    assert _calc_format_label(_cm(type_="percent")) == "Percent"


def test_currency_type_returns_currency() -> None:
    assert _calc_format_label(_cm(type_="currency")) == "Currency"


def test_time_type_returns_time() -> None:
    assert _calc_format_label(_cm(type_="time")) == "Time"


def test_decimal_type_returns_decimal() -> None:
    assert _calc_format_label(_cm(type_="decimal")) == "Decimal"


def test_precision_positive_returns_decimal_when_type_uncertain() -> None:
    assert _calc_format_label(_cm(type_="other", precision=2)) == "Decimal"


def test_uncertain_returns_none() -> None:
    """Unknown type + precision=0 → None (under-fill safer than wrong-fill)."""
    assert _calc_format_label(_cm(type_="weirdtype", precision=0)) is None


def test_percent_with_precision_returns_percent() -> None:
    """Type precedence over precision — percent + precision=2 still maps to 'Percent'."""
    assert _calc_format_label(_cm(type_="percent", precision=2)) == "Percent"


def test_case_insensitive_type_match() -> None:
    """Type matching is lowercased per implementation."""
    assert _calc_format_label(_cm(type_="PERCENT")) == "Percent"
