"""Cross-RSID inventory rollup — cli/commands/inventory.py."""

from __future__ import annotations

import json as _json
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import inventory as inv_command
from aa_auto_sdr.cli.commands.inventory import _COMPONENT_TYPES, _aggregate
from aa_auto_sdr.core.exit_codes import ExitCode


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


class _StubReportSuite:
    def __init__(self, rsid: str, name: str) -> None:
        self.rsid = rsid
        self.name = name


class _StubFetchOutcome:
    def __init__(self, data: list, status: str = "healthy", expansion_level: str = "full") -> None:
        self.data = data
        self.status = status
        self.expansion_level = expansion_level


def _stub_fetch_table(client: object, rsid: str) -> _StubReportSuite:
    return _StubReportSuite(rsid, rsid.upper())


def _patch_fetchers(*, vrs_outcome: _StubFetchOutcome | None = None, cls_outcome: _StubFetchOutcome | None = None):
    """Patch every fetcher inventory.run calls with deterministic stubs.

    Default counts (per-RSID): 100 dim, 50 met, 25 seg, 10 calc, 5 vrs, 2 cls.
    """
    vrs = vrs_outcome or _StubFetchOutcome([{"id": f"vrs{i}"} for i in range(5)])
    cls = cls_outcome or _StubFetchOutcome([{"id": f"cls{i}"} for i in range(2)])
    return [
        patch.object(inv_command.fetch, "fetch_report_suite", side_effect=_stub_fetch_table),
        patch.object(inv_command.fetch, "fetch_dimensions", return_value=[{"id": f"d{i}"} for i in range(100)]),
        patch.object(inv_command.fetch, "fetch_metrics", return_value=[{"id": f"m{i}"} for i in range(50)]),
        patch.object(inv_command.fetch, "fetch_segments", return_value=[{"id": f"s{i}"} for i in range(25)]),
        patch.object(inv_command.fetch, "fetch_calculated_metrics", return_value=[{"id": f"cm{i}"} for i in range(10)]),
        patch.object(inv_command.fetch, "fetch_virtual_report_suites", return_value=vrs),
        patch.object(inv_command.fetch, "fetch_classification_datasets", return_value=cls),
        patch.object(
            inv_command.fetch,
            "resolve_rsid",
            side_effect=lambda _client, ident, name_match="insensitive": ([ident], False),  # noqa: ARG005
        ),
        patch.object(inv_command.AaClient, "from_credentials", return_value=MagicMock()),
        patch.object(inv_command.credentials, "resolve", return_value=MagicMock()),
    ]


def _enter_all(patches: list) -> list:
    return [p.__enter__() for p in patches]


def _exit_all(patches: list) -> None:
    for p in patches:
        p.__exit__(None, None, None)


class TestRunTable:
    def test_table_renders_aggregate_and_per_rsid(self, capsys: pytest.CaptureFixture[str]) -> None:
        patches = _patch_fetchers()
        _enter_all(patches)
        try:
            exit_code = inv_command.run(
                rsids=["rs1", "rs2"],
                profile=None,
                format_name="table",
            )
        finally:
            _exit_all(patches)
        assert exit_code == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "INVENTORY SUMMARY (2 report suites)" in out
        assert "Total" in out
        assert "Min" in out
        assert "Max" in out
        assert "Avg" in out
        assert "Per-RSID" in out
        assert "rs1" in out
        assert "rs2" in out
        assert "200" in out  # totals['dimensions'] = 100 + 100

    def test_table_default_when_format_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        patches = _patch_fetchers()
        _enter_all(patches)
        try:
            exit_code = inv_command.run(
                rsids=["rs1"],
                profile=None,
                format_name=None,
            )
        finally:
            _exit_all(patches)
        assert exit_code == ExitCode.OK.value
        assert "INVENTORY SUMMARY" in capsys.readouterr().out


class TestRunJson:
    def test_json_emits_structured_object(self, capsys: pytest.CaptureFixture[str]) -> None:
        patches = _patch_fetchers()
        _enter_all(patches)
        try:
            exit_code = inv_command.run(
                rsids=["rs1", "rs2"],
                profile=None,
                format_name="json",
            )
        finally:
            _exit_all(patches)
        assert exit_code == ExitCode.OK.value
        payload = _json.loads(capsys.readouterr().out)
        assert payload["report_suites_count"] == 2
        assert payload["totals"]["dimensions"] == 200
        assert payload["min"]["dimensions"] == 100
        assert payload["max"]["dimensions"] == 100
        assert payload["avg"]["dimensions"] == 100.0
        assert len(payload["per_rsid"]) == 2
        assert payload["per_rsid"][0]["rsid"] == "rs1"


class TestRunCsv:
    def test_csv_per_rsid_matrix_with_total_row(self, capsys: pytest.CaptureFixture[str]) -> None:
        patches = _patch_fetchers()
        _enter_all(patches)
        try:
            exit_code = inv_command.run(
                rsids=["rs1", "rs2"],
                profile=None,
                format_name="csv",
            )
        finally:
            _exit_all(patches)
        assert exit_code == ExitCode.OK.value
        out = capsys.readouterr().out
        lines = [line for line in out.splitlines() if line.strip()]
        # Header + 2 RSID rows + TOTAL row
        assert len(lines) == 4
        assert lines[0].startswith("rsid,name,dimensions,metrics,")
        assert lines[1].startswith("rs1,")
        assert lines[2].startswith("rs2,")
        assert lines[3].startswith("TOTAL,")
        assert ",200," in lines[3]  # totals['dimensions']


class TestRunFormatRejection:
    def test_excel_format_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = inv_command.run(
            rsids=["rs1"],
            profile=None,
            format_name="excel",
        )
        assert exit_code == ExitCode.OUTPUT.value
        out = capsys.readouterr().out
        assert "table|json|csv" in out

    def test_html_format_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = inv_command.run(
            rsids=["rs1"],
            profile=None,
            format_name="html",
        )
        assert exit_code == ExitCode.OUTPUT.value


class TestRunNoPositional:
    def test_no_rsids_summarizes_all_visible(self, capsys: pytest.CaptureFixture[str]) -> None:
        """With no positional RSIDs, --inventory-summary defaults to all visible RSes."""
        all_summaries = [_StubReportSuite(f"rs{i}", f"RS{i}") for i in range(3)]
        patches = _patch_fetchers()
        # Override resolve_rsid (not called when rsids is empty) and add summaries fetcher.
        patches.append(patch.object(inv_command.fetch, "fetch_report_suite_summaries", return_value=all_summaries))
        _enter_all(patches)
        try:
            exit_code = inv_command.run(
                rsids=[],
                profile=None,
                format_name="json",
            )
        finally:
            _exit_all(patches)
        assert exit_code == ExitCode.OK.value
        payload = _json.loads(capsys.readouterr().out)
        assert payload["report_suites_count"] == 3


class TestRunFetchStatusFooter:
    def test_non_healthy_vrs_marks_table_with_asterisk(self, capsys: pytest.CaptureFixture[str]) -> None:
        degraded = _StubFetchOutcome(data=[], status="degraded", expansion_level="minimal")
        patches = _patch_fetchers(vrs_outcome=degraded)
        _enter_all(patches)
        try:
            inv_command.run(
                rsids=["rs1"],
                profile=None,
                format_name="json",
            )
        finally:
            _exit_all(patches)
        payload = _json.loads(capsys.readouterr().out)
        # fetch_status appears on the per-RSID row when VRS fetch is degraded.
        assert payload["per_rsid"][0]["fetch_status"]["virtual_report_suites"]["status"] == "degraded"
