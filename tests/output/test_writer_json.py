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
    assert actual == [target]
    assert target.exists()
    parsed = json.loads(target.read_text())
    assert parsed["report_suite"]["rsid"] == "x"
    assert parsed["tool_version"] == "0.1.0"


def test_json_writer_appends_extension_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "sdr"
    actual = JsonWriter().write(_doc(), target)
    assert len(actual) == 1
    assert actual[0].suffix == ".json"
    assert actual[0].exists()


def test_json_writer_emits_quality_when_present(tmp_path: Path) -> None:
    """v1.12.0 fix: JSON output now carries the quality block."""
    doc = SdrDocument(
        report_suite=models.ReportSuite(rsid="x", name="X", timezone=None, currency=None, parent_rsid=None),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="1.12.0",
        quality={"naming_audit": {"total_components": 0}},
    )
    target = tmp_path / "out.json"
    JsonWriter().write(doc, target)
    payload = json.loads(target.read_text())
    assert payload["quality"] == {"naming_audit": {"total_components": 0}}


def test_retained_payload_matches_normal_write_and_logs_conversion(tmp_path, monkeypatch, caplog):
    import logging

    from aa_auto_sdr.output.writers import json as json_writer

    doc = _doc()
    elapsed = [0.0]
    real = SdrDocument.to_dict

    def convert(self):
        elapsed[0] += 0.025
        return real(self)

    monkeypatch.setattr(SdrDocument, "to_dict", convert)
    monkeypatch.setattr(json_writer.time, "monotonic", lambda: elapsed[0])
    with caplog.at_level(logging.INFO, logger=json_writer.__name__):
        JsonWriter().write(doc, tmp_path / "normal.json")
        paths, payload = JsonWriter()._write_and_retain_payload(doc, tmp_path / "retained.json")
    assert paths == [tmp_path / "retained.json"]
    assert paths[0].read_bytes() == (tmp_path / "normal.json").read_bytes()
    assert payload == real(doc)
    records = [record for record in caplog.records if record.name == json_writer.__name__]
    assert len(records) == 2
    assert all(record.rsid == "x" and record.duration_ms == 25 for record in records)
