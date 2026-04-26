"""JSON writer: serializes SdrDocument.to_dict() via atomic write."""

import json
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.api import models
from aa_auto_sdr.output.writers.json import JsonWriter
from aa_auto_sdr.sdr.document import SdrDocument


def _doc() -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid="x",
            name="X",
            timezone="UTC",
            currency="USD",
            parent_rsid=None,
        ),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )


def test_json_writer_extension() -> None:
    assert JsonWriter().extension == ".json"


def test_json_writer_writes_valid_json(tmp_path: Path) -> None:
    target = tmp_path / "sdr.json"
    actual = JsonWriter().write(_doc(), target)
    assert actual == target
    assert target.exists()
    parsed = json.loads(target.read_text())
    assert parsed["report_suite"]["rsid"] == "x"
    assert parsed["tool_version"] == "0.1.0"


def test_json_writer_appends_extension_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "sdr"
    actual = JsonWriter().write(_doc(), target)
    assert actual.suffix == ".json"
    assert actual.exists()
