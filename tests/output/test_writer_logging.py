"""v1.5 — assert each writer emits one output_write INFO record per call,
with format/output_path/count/duration_ms/rsid extras. CSV count=7, others
count=1."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.output import registry
from aa_auto_sdr.sdr.document import SdrDocument


def _make_doc(rsid: str = "RS1") -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid=rsid,
            name=f"name-{rsid}",
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
        captured_at=datetime.now(UTC),
        tool_version="1.5.0",
    )


@pytest.fixture(autouse=True)
def _isolate_package_logger():
    """Other v1.4 tests (cli/test_main_logging.py) attach caplog handlers to
    the ``aa_auto_sdr`` package logger and don't detach. That leaks across
    tests, so records propagating through the package logger get captured
    twice — once by the leaked handler, once by current caplog on root.
    Snapshot and restore handlers so this test file is hermetic."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    pkg.handlers.clear()
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)


@pytest.fixture(autouse=True)
def _bootstrap():
    registry.bootstrap()


@pytest.mark.parametrize(
    ("format_name", "expected_count"),
    [
        ("excel", 1),
        ("csv", 7),
        ("json", 1),
        ("html", 1),
        ("markdown", 1),
    ],
)
def test_each_writer_emits_output_write_info(caplog, tmp_path, format_name, expected_count):
    caplog.set_level(logging.INFO, logger=f"aa_auto_sdr.output.writers.{format_name}")
    writer = registry.get_writer(format_name)
    target = tmp_path / f"RS1{writer.extension}"
    writer.write(_make_doc(), target)

    records = [r for r in caplog.records if "output_write" in r.getMessage()]
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.INFO
    assert rec.format == format_name
    assert isinstance(rec.output_path, str)
    assert rec.count == expected_count
    assert isinstance(rec.duration_ms, int)
    assert rec.rsid == "RS1"
