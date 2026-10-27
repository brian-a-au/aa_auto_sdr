"""Excel writer: one sheet per component type, frozen header row, autofilter."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output.writers.excel import ExcelWriter
from aa_auto_sdr.sdr.builder import build_sdr

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def doc():
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    client = AaClient(handle=handle, company_id="testco")
    return build_sdr(client, "demo.prod", captured_at=datetime(2026, 4, 25, tzinfo=UTC), tool_version="0.1.0")


def test_excel_extension() -> None:
    assert ExcelWriter().extension == ".xlsx"


def test_excel_writer_creates_file(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    actual = ExcelWriter().write(doc, target)
    assert actual == [target]
    assert target.exists()


def test_excel_replace_failure_preserves_readable_workbook(
    doc,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "sdr.xlsx"
    original = Workbook()
    original.active["A1"] = "original"
    original.save(target)
    original.close()
    original_bytes = target.read_bytes()

    def fail_replace(source: Path, destination: Path) -> None:
        raise PermissionError("destination locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)

    with pytest.raises(PermissionError, match="destination locked"):
        ExcelWriter().write(doc, target)

    assert target.read_bytes() == original_bytes
    preserved = load_workbook(target, read_only=True)
    assert preserved.active["A1"].value == "original"
    preserved.close()
    assert [path for path in tmp_path.iterdir() if path.name.startswith(".")] == []


def test_excel_has_summary_and_one_sheet_per_component(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target, read_only=True)
    expected = {
        "Summary",
        "Dimensions",
        "Metrics",
        "Segments",
        "Calculated Metrics",
        "Virtual Report Suites",
        "Classifications",
    }
    assert expected.issubset(set(wb.sheetnames))


def test_excel_freezes_header_row(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target, read_only=False)
    assert wb["Dimensions"].freeze_panes == "A2"


def test_excel_dimension_rows_match_doc(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target, read_only=True)
    sheet = wb["Dimensions"]
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][0] == "id"
    assert len(rows) == 1 + len(doc.dimensions)


def test_excel_column_widths_fit_content_capped_at_60(tmp_path: Path) -> None:
    """Column width = max(header, longest cell) + 2, capped at 60.

    Characterization for the width pass — locks rendered output across the
    single-stringify refactor (widths are computed from the already-
    stringified cells, not a second astype(str) conversion)."""
    from dataclasses import replace as dc_replace

    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    long_desc = "x" * 100
    handle.getDimensions.return_value = _df(
        [
            {"id": "evar1", "name": "A", "type": "string", "description": long_desc, "tags": []},
            {"id": "evar2", "name": "B", "type": "string", "description": "short", "tags": []},
        ],
    )
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    client = AaClient(handle=handle, company_id="testco")
    doc = build_sdr(client, "demo.prod", captured_at=datetime(2026, 4, 25, tzinfo=UTC), tool_version="0.1.0")
    doc = dc_replace(doc)

    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target)
    ws = wb["Dimensions"]
    headers = [c.value for c in ws[1]]
    id_col = chr(ord("A") + headers.index("id"))
    desc_col = chr(ord("A") + headers.index("description"))
    # xlsxwriter stores character widths with sub-unit font padding, so
    # openpyxl reads e.g. 7 as ~7.71 — assert within the one-unit band.
    # id: max(len("id")=2, len("evar1")=5) + 2 = 7
    assert 7 <= ws.column_dimensions[id_col].width < 8
    # description: 100-char cell exceeds the cap -> 60
    assert 60 <= ws.column_dimensions[desc_col].width < 61


def test_excel_nested_values_and_layout_preserve_document(doc, tmp_path: Path) -> None:
    from copy import deepcopy
    from dataclasses import fields, replace

    from aa_auto_sdr.output._helpers import stringify_cell

    segment = replace(
        doc.segments[0],
        name='=HYPERLINK("https://example.test", "雪")',
        description="雪" * 1000,
        definition={"container": {"predicates": [{"value": "café", "enabled": True}]}},
        tags=["雪", "café"],
        extra={"url": "https://example.test", "nested": [None, {"x": 1}]},
    )
    doc = replace(doc, segments=[segment], metrics=[])
    before = deepcopy(doc)
    target = tmp_path / "nested.xlsx"
    ExcelWriter().write(doc, target)
    assert doc == before
    with target.open("rb") as stream:
        wb = load_workbook(stream)
    assert wb.sheetnames == [
        "Summary",
        "Coverage",
        "Quality",
        "Dimensions",
        "Metrics",
        "Segments",
        "Calculated Metrics",
        "Virtual Report Suites",
        "Classifications",
    ]
    ws = wb["Segments"]
    headers = [f.name for f in fields(segment)]
    assert [cell.value for cell in ws[1]] == headers
    expected = [stringify_cell(getattr(segment, name)) or None for name in headers]
    assert [cell.value for cell in ws[2]] == expected
    assert all(cell.data_type != "f" and cell.hyperlink is None for cell in ws[2])
    assert len({cell.style_id for cell in ws[1]}) == 1
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:K2"
    assert wb["Metrics"].max_row == 1
    assert wb["Metrics"]["A1"].value is None
    assert wb["Metrics"].auto_filter.ref is None
    assert wb["Metrics"].freeze_panes == "A2"
    summary = {row[0].value: row[1] for row in wb["Summary"].iter_rows(min_row=2)}
    assert summary["Segments"].value == 1
    assert summary["Segments"].data_type == "n"
    assert summary["Metrics"].value == 0
    wb.close()


def test_excel_serialization_failure_preserves_existing_workbook(doc, tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    original_bytes = target.read_bytes()
    original_to_excel = pd.DataFrame.to_excel

    def fail_later_sheet(frame, writer, *, sheet_name, **kwargs):
        if sheet_name == "Segments":
            raise OSError("sheet write failed")
        return original_to_excel(frame, writer, sheet_name=sheet_name, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_excel", fail_later_sheet)
    with pytest.raises(OSError, match="sheet write failed"):
        ExcelWriter().write(doc, target)
    assert target.read_bytes() == original_bytes
    wb = load_workbook(target)
    assert wb["Summary"]["A1"].value == "Field"
    wb.close()
    assert list(tmp_path.iterdir()) == [target]
