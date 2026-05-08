"""v1.5 — assert api/fetch.py emits component_fetch INFO records and
metadata DEBUG records per the style guide."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api import fetch


def _records_with_event(caplog, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if event in r.getMessage()]


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


@pytest.mark.parametrize(
    ("fn_name", "sdk_method", "expected_component_type"),
    [
        ("fetch_dimensions", "getDimensions", "dimension"),
        ("fetch_metrics", "getMetrics", "metric"),
        ("fetch_segments", "getSegments", "segment"),
        ("fetch_calculated_metrics", "getCalculatedMetrics", "calculated_metric"),
        ("fetch_virtual_report_suites", "getVirtualReportSuites", "virtual_report_suite"),
        ("fetch_classification_datasets", "getClassificationDatasets", "classification"),
    ],
)
def test_each_component_fetcher_emits_component_fetch_info(caplog, fn_name, sdk_method, expected_component_type):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.api.fetch")
    fake_client = MagicMock()
    sdk = getattr(fake_client.handle, sdk_method)
    sdk.return_value = pd.DataFrame([{"id": "x", "name": "X", "rsid": "RS1", "parentRsid": "RS1"}])
    fn = getattr(fetch, fn_name)
    fn(fake_client, "RS1")
    records = _records_with_event(caplog, "component_fetch")
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.INFO
    assert rec.rsid == "RS1"
    assert rec.component_type == expected_component_type
    assert isinstance(rec.count, int)
    assert rec.count >= 1
    assert isinstance(rec.duration_ms, int)


def test_classifications_failure_emits_warning(caplog):
    caplog.set_level(logging.WARNING, logger="aa_auto_sdr.api.fetch")
    fake_client = MagicMock()
    fake_client.handle.getClassificationDatasets.side_effect = RuntimeError("boom")
    out = fetch.fetch_classification_datasets(fake_client, "RS1")
    assert out == []
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    rec = warnings[0]
    assert rec.rsid == "RS1"
    assert rec.component_type == "classification"
    assert rec.error_class == "RuntimeError"


def test_virtual_report_suites_failure_emits_warning(caplog):
    """v1.6.1: VRS fetch must emit the same structured WARNING as classifications
    when the SDK call raises (e.g. KeyError('content') from aanalytics2 0.5.1
    on an HTTP 500 response). rsid carries the parent_rsid for correlation."""
    caplog.set_level(logging.WARNING, logger="aa_auto_sdr.api.fetch")
    fake_client = MagicMock()
    fake_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    out = fetch.fetch_virtual_report_suites(fake_client, "RS1")
    assert out == []
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    rec = warnings[0]
    assert rec.rsid == "RS1"
    assert rec.component_type == "virtual_report_suite"
    assert rec.error_class == "KeyError"


def test_virtual_report_suite_summaries_failure_normalizes_to_api_error():
    """Discovery path normalizes SDK-side exceptions to ApiError so the CLI
    surfaces a clean exit 12. No WARNING log here — the CLI prints the error
    message itself, and the structured run_failure record at the outer layer
    already carries the error_class field."""
    from aa_auto_sdr.core.exceptions import ApiError

    fake_client = MagicMock()
    fake_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    with pytest.raises(ApiError):
        fetch.fetch_virtual_report_suite_summaries(fake_client)


def test_fetch_report_suite_debug_and_error(caplog):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch")
    fake_client = MagicMock()
    fake_client.handle.getReportSuites.return_value = pd.DataFrame([{"rsid": "OTHER", "name": "x"}])
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    with pytest.raises(ReportSuiteNotFoundError):
        fetch.fetch_report_suite(fake_client, "MISSING")

    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(getattr(r, "rsid", None) == "MISSING" for r in errors), "expected error rec carrying the requested rsid"
    assert any(hasattr(r, "count") for r in debugs), "expected debug rec carrying suites-visible count"


def test_resolve_rsid_emits_two_debug_records(caplog):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch")
    fake_client = MagicMock()
    fake_client.handle.getReportSuites.return_value = pd.DataFrame([{"rsid": "RS1", "name": "a"}])
    fetch.resolve_rsid(fake_client, "RS1")
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debugs) >= 2  # entry + success
