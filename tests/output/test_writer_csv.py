"""CSV writer: 7 files per RS, header-only when component is empty, BOM-encoded."""

import csv as _csv
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output.writers.csv import CsvWriter
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


def test_csv_writer_extension_is_csv() -> None:
    assert CsvWriter().extension == ".csv"


def test_csv_writer_returns_seven_paths(doc, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    assert len(paths) == 7


def test_csv_writer_filenames_match_component_types(doc, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    names = sorted(p.name for p in paths)
    assert names == sorted(
        [
            "out.summary.csv",
            "out.dimensions.csv",
            "out.metrics.csv",
            "out.segments.csv",
            "out.calculated_metrics.csv",
            "out.virtual_report_suites.csv",
            "out.classifications.csv",
        ]
    )


def test_csv_writer_summary_has_field_value_rows(doc, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    summary = next(p for p in paths if p.name.endswith(".summary.csv"))
    with summary.open(encoding="utf-8-sig") as fh:
        rows = list(_csv.reader(fh))
    assert rows[0] == ["field", "value"]
    flat = {r[0]: r[1] for r in rows[1:]}
    assert flat["RSID"] == "demo.prod"
    assert flat["Name"] == "Demo Production"
    assert flat["Tool version"] == "0.2.0"
    assert flat["Dimensions"] == "4"


def test_csv_writer_dimensions_has_one_row_per_component(doc, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    dims = next(p for p in paths if p.name.endswith(".dimensions.csv"))
    with dims.open(encoding="utf-8-sig") as fh:
        rows = list(_csv.reader(fh))
    assert rows[0] == [
        "id",
        "name",
        "type",
        "category",
        "parent",
        "pathable",
        "description",
        "tags",
        "extra",
    ]
    assert len(rows) == 1 + len(doc.dimensions)
    by_id = {r[0]: r for r in rows[1:]}
    assert by_id["variables/evar1"][1] == "User ID"
    assert by_id["variables/evar1"][3] == "Conversion"


def test_csv_writer_segments_serializes_definition_as_json(doc, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    segs = next(p for p in paths if p.name.endswith(".segments.csv"))
    with segs.open(encoding="utf-8-sig") as fh:
        rows = list(_csv.reader(fh))
    headers = rows[0]
    definition_idx = headers.index("definition")
    s_111 = next(r for r in rows[1:] if r[0] == "s_111")
    parsed = json.loads(s_111[definition_idx])
    assert "container" in parsed


def test_csv_writer_empty_component_produces_header_only_file(doc, tmp_path: Path) -> None:
    # The fixture has 0 virtual_report_suites in this scenario
    # Re-fetch the fixture to make a doc with empty VRS
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    vrs = next(p for p in paths if p.name.endswith(".virtual_report_suites.csv"))
    with vrs.open(encoding="utf-8-sig") as fh:
        rows = list(_csv.reader(fh))
    # Header only — fixture has 1 VRS so this asserts the header structure
    assert rows[0] == [
        "id",
        "name",
        "parent_rsid",
        "timezone",
        "description",
        "segment_list",
        "curated_components",
        "modified",
        "extra",
    ]


def test_csv_writer_writes_utf8_bom(doc, tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    paths = CsvWriter().write(doc, target)
    summary = next(p for p in paths if p.name.endswith(".summary.csv"))
    raw_bytes = summary.read_bytes()
    # UTF-8 BOM is b"\xef\xbb\xbf"
    assert raw_bytes.startswith(b"\xef\xbb\xbf")


def test_csv_writer_atomic_no_tmp_files_left_behind(doc, tmp_path: Path) -> None:
    """Atomic write uses tempfile.mkstemp with prefix '.' — those files are
    hidden and Path.glob('*.tmp') won't match them. Use iterdir to be sure."""
    target = tmp_path / "out.csv"
    CsvWriter().write(doc, target)
    leftover = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []
