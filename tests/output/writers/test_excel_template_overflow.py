"""Template fill keeps every clipped row and reports its own coverage.

The `max_row + 50` soft cap still bounds what lands inside a template sheet.
Rows past the cap go to a separate `Overflow` sheet instead of being dropped,
and a `Template Coverage` sheet reports what landed where. Workbooks are read
back with openpyxl, the same way a reader of the filled file would."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName

from aa_auto_sdr.api import models
from aa_auto_sdr.output.writers.excel_template import ExcelTemplateWriter
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument

_LOGGER = "aa_auto_sdr.output.writers.excel_template"
_ALL_FAMILIES = (
    "calculated_metrics",
    "classifications",
    "dimensions",
    "metrics",
    "segments",
    "virtual_report_suites",
)


def _calc(i: int) -> models.CalculatedMetric:
    return models.CalculatedMetric(
        id=f"cm_{i:04d}",
        name=f"Calc {i}",
        description=f"Calc desc {i}",
        rsid="test_rs",
        owner_id=None,
        polarity="positive",
        precision=0,
        type="percent",
        definition={},
    )


def _seg(i: int, name: str | None = None) -> models.Segment:
    return models.Segment(
        id=f"s_{i:04d}",
        name=name or f"Seg {i}",
        description=f"Seg desc {i}",
        rsid="test_rs",
        owner_id=None,
        definition={},
    )


def _dim(id_: str, name: str) -> models.Dimension:
    return models.Dimension(
        id=id_,
        name=name,
        type="string",
        category=None,
        parent="",
        pathable=False,
        description=f"{name} desc",
    )


def _doc(
    *,
    dimensions: list[models.Dimension] | None = None,
    segments: list[models.Segment] | None = None,
    calculated_metrics: list[models.CalculatedMetric] | None = None,
    collected: tuple[str, ...] | None = _ALL_FAMILIES,
    fetch_status: dict[str, FetchOutcomeMeta] | None = None,
) -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid="test_rs",
            name="Test Report Suite",
            timezone="UTC",
            currency=None,
            parent_rsid=None,
        ),
        dimensions=dimensions or [],
        metrics=[],
        segments=segments or [],
        calculated_metrics=calculated_metrics or [],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 10, 27, tzinfo=UTC),
        tool_version="test",
        fetch_status=fetch_status or {},
        collected_components=collected,
    )


def _decorate_template(path: Path) -> None:
    """Add styles, an in-sheet formula, and a defined name to the synthetic
    template so preservation can be asserted after an overflowing fill."""
    wb = load_workbook(path)
    ws = wb["metrics-segments"]
    for col in range(2, 7):
        cell = ws.cell(row=6, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    ws["H2"] = "=COUNTA(D7:D1000)"
    wb["eVars"]["F2"] = "=SUM(1,2)"
    wb.defined_names["OrgName"] = DefinedName("OrgName", attr_text="Glossary!$C$2")
    wb.save(path)


def _write(template: Path, out: Path, doc: SdrDocument) -> Path:
    writer = ExcelTemplateWriter()
    writer.template_path = template
    writer.write(doc, out)
    return out


def _table(ws, header_first: str) -> list[dict[str, Any]]:
    """Read a header-led block (header row whose column A equals
    `header_first`) until the first blank row."""
    header_row = next(r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == header_first)
    headers = [ws.cell(row=header_row, column=c).value for c in range(1, ws.max_column + 1)]
    rows: list[dict[str, Any]] = []
    for r in range(header_row + 1, ws.max_row + 2):
        values = [ws.cell(row=r, column=c).value for c in range(1, len(headers) + 1)]
        if all(v is None for v in values):
            break
        rows.append({h: v for h, v in zip(headers, values, strict=True) if h is not None})
    return rows


def _template_sheet_rows(ws) -> list[dict[str, Any]]:
    """metrics-segments data rows (Type, Name, Description, Format)."""
    rows = []
    for r in range(7, ws.max_row + 1):
        name = ws.cell(row=r, column=4).value
        if name is None:
            continue
        rows.append(
            {
                "Type": ws.cell(row=r, column=3).value,
                "Name": name,
                "Description": ws.cell(row=r, column=5).value,
                "Format": ws.cell(row=r, column=6).value,
            }
        )
    return rows


@pytest.mark.parametrize("total", [51, 100, 500])
def test_every_metrics_segments_row_is_recoverable(synthetic_template_path: Path, tmp_path: Path, total: int) -> None:
    _decorate_template(synthetic_template_path)
    n_calc = total // 2 + 1
    calcs = [_calc(i) for i in range(n_calc)]
    segs = [_seg(i) for i in range(total - n_calc)]
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(calculated_metrics=calcs, segments=segs))
    wb = load_workbook(out)

    in_sheet = _template_sheet_rows(wb["metrics-segments"])
    assert len(in_sheet) == 50  # soft cap still bounds the template sheet
    assert "Overflow" in wb.sheetnames
    overflow = _table(wb["Overflow"], "Template Sheet")
    assert len(overflow) == total - 50
    assert {o["Template Sheet"] for o in overflow} == {"metrics-segments"}

    recovered = {(r["Type"], r["Name"]) for r in in_sheet} | {(o["Component Type"], o["Name"]) for o in overflow}
    expected = {("Calculated Metric", c.name) for c in calcs} | {("Segment", s.name) for s in segs}
    assert recovered == expected
    assert len(in_sheet) + len(overflow) == total  # nothing duplicated

    # Identity and values survive in the Overflow sheet.
    by_id = {o["Component ID"]: o for o in overflow}
    assert set(by_id) == {c.id for c in calcs[50:]} | {s.id for s in segs} - {s.id for s in segs[: max(0, 50 - n_calc)]}
    for seg in segs:
        if seg.id in by_id:
            row = by_id[seg.id]
            assert row["Type"] == "Segment"
            assert row["Description"] == seg.description
            assert row.get("Format") is None
    for cm in calcs:
        if cm.id in by_id:
            assert by_id[cm.id]["Format"] == "Percent"

    # Segments clipped by calc metrics are visible, not lost.
    assert any(o["Component Type"] == "Segment" for o in overflow)

    # Template formulas, styles, and defined names survive.
    ws = wb["metrics-segments"]
    assert ws["C2"].value == "=Glossary!C2"
    assert ws["H2"].value == "=COUNTA(D7:D1000)"
    assert wb["eVars"]["F2"].value == "=SUM(1,2)"
    assert ws.cell(row=6, column=3).font.bold is True
    assert ws.cell(row=6, column=3).fill.fgColor.rgb.endswith("1F4E78")
    assert "OrgName" in wb.defined_names

    coverage = {r["Template Sheet"]: r for r in _table(wb["Template Coverage"], "Template Sheet")}
    ms = coverage["metrics-segments"]
    assert ms["Status"] == "filled"
    assert ms["Components"] == total
    assert ms["Rows Appended"] == 50
    assert ms["Rows In Overflow"] == total - 50


def test_no_overflow_sheet_when_everything_fits(synthetic_template_path: Path, tmp_path: Path) -> None:
    out = _write(
        synthetic_template_path,
        tmp_path / "out.xlsx",
        _doc(calculated_metrics=[_calc(0)], segments=[_seg(0)]),
    )
    wb = load_workbook(out)
    assert "Overflow" not in wb.sheetnames
    assert wb.sheetnames[-1] == "Template Coverage"
    summary = {r["Measure"]: r["Value"] for r in _table(wb["Template Coverage"], "Measure")}
    assert summary["Rows sent to Overflow"] == 0
    assert summary["Rows appended"] == 2


def test_by_id_sheet_overflow_keeps_identity_and_values(synthetic_template_path: Path, tmp_path: Path) -> None:
    # evar1/evar2 match template rows; 60 API-only eVars hit the soft cap.
    dims = [_dim("variables/evar1", "Customer ID")] + [_dim(f"variables/evar{i}", f"Var {i}") for i in range(100, 160)]
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(dimensions=dims))
    wb = load_workbook(out)
    ws = wb["eVars"]
    in_sheet = {ws.cell(row=r, column=3).value for r in range(7, ws.max_row + 1)} - {None}
    overflow = _table(wb["Overflow"], "Template Sheet")
    assert {o["Template Sheet"] for o in overflow} == {"eVars"}
    assert {o["Component Type"] for o in overflow} == {"Dimension"}
    overflow_ids = {o["Component ID"] for o in overflow}
    assert not overflow_ids & in_sheet
    assert {f"evar{i}" for i in range(100, 160)} | {"evar1"} <= in_sheet | overflow_ids
    first = overflow[0]
    assert first["Analytics Variable"] == first["Component ID"]
    assert first["Variable Name"].startswith("Var ")
    assert first["Variable Description"].endswith(" desc")

    coverage = {r["Template Sheet"]: r for r in _table(wb["Template Coverage"], "Template Sheet")}
    assert coverage["eVars"]["Rows Matched"] == 1
    assert coverage["eVars"]["Rows Appended"] + coverage["eVars"]["Rows In Overflow"] == 60
    assert coverage["eVars"]["Rows In Overflow"] == len(overflow)


def test_overflow_logs_written_event_and_keeps_clip_event(
    synthetic_template_path: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER)
    _write(
        synthetic_template_path,
        tmp_path / "out.xlsx",
        _doc(calculated_metrics=[_calc(i) for i in range(60)], segments=[_seg(0)]),
    )
    clipped = [r for r in caplog.records if r.message.startswith("template_sheet_clipped ")]
    assert clipped
    assert clipped[0].rows_dropped == 11
    written = [r for r in caplog.records if r.message.startswith("template_overflow_sheet_written ")]
    assert len(written) == 1
    assert written[0].levelno == logging.WARNING
    assert written[0].sheet == "Overflow"
    assert written[0].count == 11


def test_coverage_reports_missing_sheets_columns_and_family_states(
    synthetic_template_path: Path, tmp_path: Path
) -> None:
    wb = load_workbook(synthetic_template_path)
    del wb["props"]
    wb["custom events (metrics)"]["B4"] = "Something Else"  # anchor mismatch
    wb["eVars"].cell(row=6, column=6, value="eVar Allocation")  # writer can't fill this
    wb["metrics-segments"]["F6"].value = None  # template lacks Format
    wb.save(synthetic_template_path)

    doc = _doc(
        dimensions=[_dim("variables/prop5", "Prop Five"), _dim("variables/evar1", "Customer ID")],
        collected=("dimensions", "metrics", "segments", "virtual_report_suites"),
        fetch_status={"virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None)},
    )
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", doc)
    cov_ws = load_workbook(out)["Template Coverage"]

    sheets = {r["Template Sheet"]: r for r in _table(cov_ws, "Template Sheet")}
    assert sheets["props"]["Status"] == "skipped"
    assert sheets["props"]["Reason"] == "missing_or_unanchored"
    assert sheets["props"]["Components"] == 1  # prop5 had nowhere to go
    assert sheets["custom events (metrics)"]["Status"] == "skipped"
    assert sheets["eVars"]["Status"] == "filled"
    assert sheets["eVars"]["Unsupported Columns"] == "eVar Allocation"
    assert sheets["eVars"].get("Missing Columns") is None
    assert sheets["metrics-segments"]["Missing Columns"] == "Format"
    assert sheets["Glossary"]["Status"] == "filled"

    families = {r["Family"]: r for r in _table(cov_ws, "Family")}
    assert families["Dimensions"]["State"] == "Collected"
    assert families["Dimensions"]["Template Sheets"] == "eVars, props"
    assert families["Calculated Metrics"]["State"] == "Not collected in this capture"
    assert families["Segments"]["State"] == "Collected — no components"
    assert families["Virtual Report Suites"]["State"] == "Fetch degraded — no data"
    assert families["Virtual Report Suites"]["Template Sheets"] == "not in template"

    summary = {r["Measure"]: r["Value"] for r in _table(cov_ws, "Measure")}
    assert summary["Sheets skipped"] == 2
    assert summary["Quality"] == "No quality audit ran."


def test_unknown_scope_is_reported_as_unknown(synthetic_template_path: Path, tmp_path: Path) -> None:
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(collected=None))
    families = {r["Family"]: r for r in _table(load_workbook(out)["Template Coverage"], "Family")}
    assert families["Segments"]["State"] == "Scope unknown — may not have been collected"


def test_overflow_values_never_become_live_formulas(synthetic_template_path: Path, tmp_path: Path) -> None:
    segs = [_seg(i) for i in range(50)] + [_seg(99, name='=HYPERLINK("http://x")')]
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(segments=segs))
    ws = load_workbook(out)["Overflow"]
    cells = [c for row in ws.iter_rows() for c in row if c.value == '=HYPERLINK("http://x")']
    assert cells
    assert all(c.data_type != "f" for c in cells)


def test_existing_overflow_and_coverage_sheets_are_not_clobbered(synthetic_template_path: Path, tmp_path: Path) -> None:
    wb = load_workbook(synthetic_template_path)
    wb.create_sheet("Overflow")["A1"] = "customer notes"
    wb.create_sheet("Template Coverage")["A1"] = "customer coverage"
    wb.save(synthetic_template_path)

    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(segments=[_seg(i) for i in range(55)]))
    wb = load_workbook(out)
    assert wb["Overflow"]["A1"].value == "customer notes"
    assert wb["Template Coverage"]["A1"].value == "customer coverage"
    assert len(_table(wb["Overflow (2)"], "Template Sheet")) == 5
    assert "Measure" in {c.value for c in wb["Template Coverage (2)"]["A"]}


def test_overflow_skips_columns_the_template_lacks_and_empty_values(
    synthetic_template_path: Path, tmp_path: Path
) -> None:
    wb = load_workbook(synthetic_template_path)
    wb["metrics-segments"]["E6"].value = None  # no Description column
    wb.save(synthetic_template_path)
    blank = models.Segment(id="s_blank", name="  ", description="Has text", rsid="r", owner_id=None, definition={})
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(segments=[_seg(i) for i in range(50)] + [blank]))
    (row,) = _table(load_workbook(out)["Overflow"], "Template Sheet")
    assert row == {
        "Template Sheet": "metrics-segments",
        "Component Type": "Segment",
        "Component ID": "s_blank",
        "Type": "Segment",
    }


def test_overflow_sheet_name_counts_past_existing_suffixes(synthetic_template_path: Path, tmp_path: Path) -> None:
    wb = load_workbook(synthetic_template_path)
    wb.create_sheet("Overflow")
    wb.create_sheet("Overflow (2)")
    wb.save(synthetic_template_path)
    out = _write(synthetic_template_path, tmp_path / "out.xlsx", _doc(segments=[_seg(i) for i in range(51)]))
    assert "Overflow (3)" in load_workbook(out).sheetnames
