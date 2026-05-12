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


def _dim(id_: str, name: str, description: str | None = None) -> models.Dimension:
    return models.Dimension(
        id=id_,
        name=name,
        type="string",
        category=None,
        parent="",
        pathable=False,
        description=description,
    )


def test_dimension_match_by_id_overwrites_preseeded_evars(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    dims = [
        _dim("evar1", "Customer ID", "Logged-in customer hash"),
        _dim("evar2", "Cart ID", "Active cart token"),
    ]
    writer.write(_doc(dimensions=dims), out)
    wb = load_workbook(out)
    ws = wb["eVars"]
    # eVar1 at row 7 was pre-seeded; should be overwritten
    assert ws.cell(row=7, column=3).value == "evar1"  # Analytics Variable col
    assert ws.cell(row=7, column=4).value == "Customer ID"
    assert ws.cell(row=7, column=5).value == "Logged-in customer hash"
    # eVar2 at row 8
    assert ws.cell(row=8, column=4).value == "Cart ID"


def test_dimension_skeleton_rows_with_no_api_match_untouched(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    """eVar37 is a template-only skeleton row; API has no eVar37 → leave it."""
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    writer.write(_doc(dimensions=[_dim("evar1", "Customer ID")]), out)
    wb = load_workbook(out)
    ws = wb["eVars"]
    # Row 9 was eVar37 skeleton; untouched
    assert ws.cell(row=9, column=3).value == "evar37"
    assert ws.cell(row=9, column=4).value == "Skeleton eVar 37"


def test_dimension_match_is_case_insensitive(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    """Template has 'evar1'; API returns 'eVar1' — must still match."""
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    writer.write(_doc(dimensions=[_dim("eVar1", "Customer ID")]), out)
    wb = load_workbook(out)
    ws = wb["eVars"]
    assert ws.cell(row=7, column=4).value == "Customer ID"


def test_dimension_blank_description_does_not_overwrite_existing(
    synthetic_template_path: Path,
    tmp_path: Path,
) -> None:
    """Rule §3.7: don't blank-overwrite when our value is None/empty."""
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    writer.write(_doc(dimensions=[_dim("evar1", "Customer ID", description=None)]), out)
    wb = load_workbook(out)
    ws = wb["eVars"]
    # Description column should keep the pre-seeded value, not become blank.
    assert ws.cell(row=7, column=5).value == "Pre-seeded desc 1"


def test_props_match_by_id(synthetic_template_path: Path, tmp_path: Path) -> None:
    """pageName is reserved/pre-seeded; API match should overwrite."""
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_path
    out = tmp_path / "out.xlsx"
    writer.write(
        _doc(
            dimensions=[
                _dim("prop1", "Internal Section"),
                _dim("pageName", "Page Name", "Canonical URL path"),
            ],
        ),
        out,
    )
    wb = load_workbook(out)
    ws = wb["props"]
    # prop1 at row 7
    assert ws.cell(row=7, column=4).value == "Internal Section"
    # pageName at row 8 (reserved, overwritten)
    assert ws.cell(row=8, column=4).value == "Page Name"
    assert ws.cell(row=8, column=5).value == "Canonical URL path"


def test_evars_sheet_filtering_includes_campaign_excludes_prop(
    synthetic_template_with_campaign_skeleton: Path,
    tmp_path: Path,
) -> None:
    """eVars sheet gets evar*-prefixed dims + 'campaign'; props get prop*+pageName/linkName."""
    writer = ExcelTemplateWriter()
    writer.template_path = synthetic_template_with_campaign_skeleton
    out = tmp_path / "out.xlsx"
    writer.write(
        _doc(
            dimensions=[
                _dim("campaign", "Tracking Code"),
                _dim("prop1", "Internal Section"),  # should not appear in eVars sheet
            ],
        ),
        out,
    )
    wb = load_workbook(out)
    # campaign overwrites the pre-seeded row at eVars row 10
    assert wb["eVars"].cell(row=10, column=3).value == "campaign"
    assert wb["eVars"].cell(row=10, column=4).value == "Tracking Code"
    # prop1 lands in props sheet, not eVars
    assert wb["props"].cell(row=7, column=4).value == "Internal Section"
