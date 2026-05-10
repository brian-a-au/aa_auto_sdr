"""Cross-RSID inventory rollup — cli/commands/inventory.py."""

from __future__ import annotations

from aa_auto_sdr.cli.commands.inventory import _COMPONENT_TYPES, _aggregate


def _row(rsid: str, **counts: int) -> dict:
    full = dict.fromkeys(_COMPONENT_TYPES, 0)
    full.update(counts)
    return {"rsid": rsid, "name": rsid.upper(), "counts": full}


class TestAggregateEmpty:
    def test_empty_list_returns_zeros(self) -> None:
        result = _aggregate([])
        assert result["report_suites_count"] == 0
        for ct in _COMPONENT_TYPES:
            assert result["totals"][ct] == 0
            assert result["min"][ct] == 0
            assert result["max"][ct] == 0
            assert result["avg"][ct] == 0


class TestAggregateSingleRow:
    def test_single_row_min_eq_max_eq_avg(self) -> None:
        rows = [_row("rs1", dimensions=10, metrics=5)]
        result = _aggregate(rows)
        assert result["report_suites_count"] == 1
        assert result["totals"]["dimensions"] == 10
        assert result["min"]["dimensions"] == 10
        assert result["max"]["dimensions"] == 10
        assert result["avg"]["dimensions"] == 10.0


class TestAggregateMultipleRows:
    def test_totals_sum_correctly(self) -> None:
        rows = [
            _row("rs1", dimensions=100, metrics=50),
            _row("rs2", dimensions=200, metrics=75),
            _row("rs3", dimensions=300, metrics=100),
        ]
        result = _aggregate(rows)
        assert result["report_suites_count"] == 3
        assert result["totals"]["dimensions"] == 600
        assert result["totals"]["metrics"] == 225

    def test_min_max_correct(self) -> None:
        rows = [
            _row("rs1", dimensions=100),
            _row("rs2", dimensions=200),
            _row("rs3", dimensions=300),
        ]
        result = _aggregate(rows)
        assert result["min"]["dimensions"] == 100
        assert result["max"]["dimensions"] == 300

    def test_avg_rounded_to_one_decimal(self) -> None:
        rows = [
            _row("rs1", dimensions=10),
            _row("rs2", dimensions=20),
            _row("rs3", dimensions=15),
        ]
        result = _aggregate(rows)
        assert result["avg"]["dimensions"] == 15.0

    def test_avg_with_uneven_division(self) -> None:
        rows = [
            _row("rs1", dimensions=10),
            _row("rs2", dimensions=11),
            _row("rs3", dimensions=12),
        ]
        result = _aggregate(rows)
        assert result["avg"]["dimensions"] == 11.0

    def test_zero_counts_supported(self) -> None:
        rows = [_row("rs1"), _row("rs2")]
        result = _aggregate(rows)
        assert result["totals"]["classifications"] == 0
        assert result["min"]["classifications"] == 0
        assert result["max"]["classifications"] == 0
        assert result["avg"]["classifications"] == 0.0
