"""Report writers show render provenance only for documents rebuilt by --render-from."""

from __future__ import annotations

import csv
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.output.writers.csv import CsvWriter
from aa_auto_sdr.output.writers.excel import ExcelWriter
from aa_auto_sdr.output.writers.html import HtmlWriter
from aa_auto_sdr.output.writers.json import JsonWriter
from aa_auto_sdr.output.writers.markdown import MarkdownWriter
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, RenderProvenance, SdrDocument

CAPTURED = datetime(2026, 4, 25, 17, 30, tzinfo=UTC)
RENDERED = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def _doc(*, rendered: bool) -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(rsid="rs1", name="RS One", timezone=None, currency=None, parent_rsid=None),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=CAPTURED,
        tool_version="1.20.0",
        collected_components=COMPONENT_FAMILIES,
        rendered=RenderProvenance(rendered_at=RENDERED, tool_version="9.9.9") if rendered else None,
    )


def test_markdown_header_names_render_and_capture(tmp_path: Path) -> None:
    out = tmp_path / "x.md"
    MarkdownWriter().write(_doc(rendered=True), out)
    text = out.read_text(encoding="utf-8")
    assert f"Rendered at {RENDERED.isoformat()} by tool version 9.9.9" in text
    assert f"from a capture taken at {CAPTURED.isoformat()}" in text
    assert "| Rendered by tool version | 9.9.9 |" in text


def test_html_header_names_render_and_capture(tmp_path: Path) -> None:
    out = tmp_path / "x.html"
    HtmlWriter().write(_doc(rendered=True), out)
    text = out.read_text(encoding="utf-8")
    assert f"from a capture taken at {CAPTURED.isoformat()}" in text
    assert "Rendered by tool version" in text


def test_csv_summary_carries_render_rows(tmp_path: Path) -> None:
    paths = CsvWriter().write(_doc(rendered=True), tmp_path / "x.csv")
    summary = next(p for p in paths if p.name.endswith(".summary.csv"))
    rows = dict(csv.reader(summary.read_text(encoding="utf-8-sig").splitlines()))
    assert rows["Captured at"] == CAPTURED.isoformat()
    assert rows["Rendered at"] == RENDERED.isoformat()
    assert rows["Rendered by tool version"] == "9.9.9"


def test_excel_summary_carries_render_rows(tmp_path: Path) -> None:
    import pandas as pd

    out = tmp_path / "x.xlsx"
    ExcelWriter().write(_doc(rendered=True), out)
    summary = pd.read_excel(out, sheet_name="Summary")
    pairs = dict(zip(summary["Field"], summary["Value"], strict=True))
    assert pairs["Rendered at"] == RENDERED.isoformat()
    assert pairs["Rendered by tool version"] == "9.9.9"


def test_json_carries_additive_render_keys(tmp_path: Path) -> None:
    out = tmp_path / "x.json"
    JsonWriter().write(_doc(rendered=True), out)
    payload = json.loads(out.read_text())
    assert payload["captured_at"] == CAPTURED.isoformat()
    assert payload["tool_version"] == "1.20.0"
    assert payload["rendered_at"] == RENDERED.isoformat()
    assert payload["rendered_by_tool_version"] == "9.9.9"


@pytest.mark.parametrize("writer_cls", [MarkdownWriter, HtmlWriter, CsvWriter, JsonWriter])
def test_live_capture_output_has_no_render_provenance(writer_cls, tmp_path: Path) -> None:
    paths = writer_cls().write(_doc(rendered=False), tmp_path / f"x{writer_cls.extension}")
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        assert "Rendered" not in text
        assert "rendered_" not in text


def test_render_field_defaults_to_none() -> None:
    names = {f.name: f.default for f in dataclasses.fields(SdrDocument)}
    assert names["rendered"] is None
