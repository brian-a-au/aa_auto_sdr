"""ExcelTemplateWriter integration tests against a synthetic template. v1.16.0."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from aa_auto_sdr.api import models
from aa_auto_sdr.output import registry
from aa_auto_sdr.output.writers.excel_template import ExcelTemplateWriter
from aa_auto_sdr.sdr.document import SdrDocument


def _doc(
    *,
    rsid: str = "test_rs",
    dimensions: list[models.Dimension] | None = None,
    metrics: list[models.Metric] | None = None,
    segments: list[models.Segment] | None = None,
    calculated_metrics: list[models.CalculatedMetric] | None = None,
) -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid=rsid,
            name="Test Report Suite",
            timezone="UTC",
            currency=None,
            parent_rsid=None,
        ),
        dimensions=dimensions or [],
        metrics=metrics or [],
        segments=segments or [],
        calculated_metrics=calculated_metrics or [],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 5, 12, 0, 0, 0, tzinfo=UTC),
        tool_version="1.16.0",
    )


def test_writer_registers_under_excel_template_key() -> None:
    registry.bootstrap()
    assert registry.get_writer("excel-template").extension == ".xlsx"


def test_write_raises_without_template_path(tmp_path: Path) -> None:
    writer = ExcelTemplateWriter()
    with pytest.raises(RuntimeError, match="template_path"):
        writer.write(_doc(), tmp_path / "out.xlsx")


def test_write_round_trip_preserves_untouched_cells(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    paths = writer.write(_doc(), out)
    assert paths == [out]
    assert out.exists()
    wb = load_workbook(out)
    assert wb["eVars"]["C1"].value == "Adobe Analytics"
    assert wb["eVars"]["C2"].value == "=Glossary!C2"
    assert wb["eVars"]["B4"].value == "eVars"


def test_glossary_c2_defaults_to_report_suite_name(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    writer.write(_doc(rsid="my_rs"), out)
    wb = load_workbook(out)
    assert wb["Glossary"]["C2"].value == "Test Report Suite"


def test_glossary_c2_uses_organization_override(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    writer.organization = "Acme Corp"
    out = tmp_path / "out.xlsx"
    writer.write(_doc(), out)
    wb = load_workbook(out)
    assert wb["Glossary"]["C2"].value == "Acme Corp"


def test_cross_sheet_formula_still_present_after_glossary_write(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    """The cross-sheet formula on every non-Glossary C2 must survive."""
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    writer.write(_doc(), out)
    wb = load_workbook(out)
    for sheet in ("eVars", "props", "custom events (metrics)", "metrics-segments"):
        assert wb[sheet]["C2"].value == "=Glossary!C2", sheet
