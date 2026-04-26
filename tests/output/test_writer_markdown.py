"""Markdown writer: GFM tables, one H2 per component, escaped pipes."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from aa_auto_sdr.output.writers.markdown import MarkdownWriter

from aa_auto_sdr.api.client import AaClient
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


def test_markdown_extension() -> None:
    assert MarkdownWriter().extension == ".md"


def test_markdown_writer_creates_single_file(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.md"
    paths = MarkdownWriter().write(doc, target)
    assert paths == [target]
    assert target.exists()


def test_markdown_has_h1_with_name_and_rsid(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.md"
    MarkdownWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    assert "# SDR — Demo Production (demo.prod)" in content


def test_markdown_has_h2_per_component_type(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.md"
    MarkdownWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    for heading in (
        "## Summary",
        "## Dimensions",
        "## Metrics",
        "## Segments",
        "## Calculated Metrics",
        "## Virtual Report Suites",
        "## Classifications",
    ):
        assert heading in content


def test_markdown_dimension_table_has_correct_headers(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.md"
    MarkdownWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    expected_header = "| id | name | type | category | parent | pathable | description | tags | extra |"
    assert expected_header in content


def test_markdown_segments_definition_inline_as_json_in_backticks(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.md"
    MarkdownWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    # Segment s_111 has a non-empty definition. Should appear as `{...}` in a cell.
    assert "s_111" in content
    # Look for backtick-wrapped JSON containing 'container'
    assert "`{" in content and "container" in content


def test_markdown_empty_section_renders_none_marker(tmp_path: Path) -> None:
    """Build a doc with no metrics/segments/etc. and verify the (none) marker renders."""
    from aa_auto_sdr.api import models as m
    from aa_auto_sdr.sdr.document import SdrDocument

    minimal = SdrDocument(
        report_suite=m.ReportSuite(
            rsid="x",
            name="X",
            timezone=None,
            currency=None,
            parent_rsid=None,
        ),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.2.0",
    )
    target = tmp_path / "empty.md"
    MarkdownWriter().write(minimal, target)
    content = target.read_text(encoding="utf-8")
    assert "_(none)_" in content


def test_markdown_escapes_pipe_characters_in_cells(tmp_path: Path) -> None:
    """A description containing a pipe must be escaped so it doesn't break the table."""
    from aa_auto_sdr.api import models as m
    from aa_auto_sdr.sdr.document import SdrDocument

    doc = SdrDocument(
        report_suite=m.ReportSuite(
            rsid="x",
            name="X",
            timezone=None,
            currency=None,
            parent_rsid=None,
        ),
        dimensions=[
            m.Dimension(
                id="d1",
                name="Has|Pipe",
                type="string",
                category=None,
                parent="",
                pathable=False,
                description="line1\nline2",
                tags=[],
                extra={},
            ),
        ],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.2.0",
    )
    target = tmp_path / "esc.md"
    MarkdownWriter().write(doc, target)
    content = target.read_text(encoding="utf-8")
    assert r"Has\|Pipe" in content
    assert "line1<br>line2" in content


def test_markdown_appends_extension_if_missing(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr"
    paths = MarkdownWriter().write(doc, target)
    assert len(paths) == 1
    assert paths[0].suffix == ".md"
    assert paths[0].exists()
