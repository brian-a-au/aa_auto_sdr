"""HTML writer: single self-contained file with embedded CSS, one section per component."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output.writers.html import HtmlWriter
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
    return build_sdr(
        client,
        "demo.prod",
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.2.0",
    )


def test_html_writer_creates_single_file(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.html"
    paths = HtmlWriter().write(doc, target)
    assert paths == [target]
    assert target.exists()


def test_html_contains_doctype_and_charset(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.html"
    HtmlWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    assert content.startswith(("<!doctype html>", "<!DOCTYPE html>"))
    assert 'charset="utf-8"' in content.lower()


def test_html_contains_one_section_per_component(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.html"
    HtmlWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    for section in (
        "Summary",
        "Dimensions",
        "Metrics",
        "Segments",
        "Calculated Metrics",
        "Virtual Report Suites",
        "Classifications",
    ):
        assert f">{section}<" in content or f">{section} <" in content


def test_html_contains_embedded_css(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.html"
    HtmlWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    assert "<style>" in content
    assert "</style>" in content


def test_html_escapes_dimension_names(doc, tmp_path: Path) -> None:
    unsafe_name = '<script>alert("example")</script> & more'
    doc = replace(doc, dimensions=[replace(doc.dimensions[0], name=unsafe_name)])
    target = tmp_path / "sdr.html"
    HtmlWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(&quot;example&quot;)&lt;/script&gt; &amp; more" in content
    assert unsafe_name not in content


def test_html_appends_extension_if_missing(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr"  # no .html suffix
    paths = HtmlWriter().write(doc, target)
    assert len(paths) == 1
    assert paths[0].suffix == ".html"
    assert paths[0].exists()


def test_html_dimensions_rows_match_doc_count(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.html"
    HtmlWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    # Each dimension produces one <tr> in the dimensions <tbody>.
    # We don't parse HTML; just check the dimension IDs appear.
    for dim_id in ("variables/evar1", "variables/evar2", "variables/prop1", "variables/events"):
        assert dim_id in content


def test_html_replace_failure_leaves_absent_destination_absent(
    doc,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "sdr.html"

    def fail_replace(source: Path, destination: Path) -> None:
        raise PermissionError("destination locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)

    with pytest.raises(PermissionError, match="destination locked"):
        HtmlWriter().write(doc, target)

    assert not target.exists()
    assert [path for path in tmp_path.iterdir() if path.name.startswith(".")] == []
