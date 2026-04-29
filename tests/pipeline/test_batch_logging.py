"""v1.4 — assert run_batch emits per-RSID lifecycle events plus the batch
summary record. Asserts the de-dup rule (no second run_start)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.core.exceptions import ApiError
from aa_auto_sdr.pipeline.batch import run_batch
from aa_auto_sdr.pipeline.models import RunResult


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


def _records_with_event(caplog, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if event in r.getMessage()]


def _fake_run_result(rsid: str) -> RunResult:
    return RunResult(
        rsid=rsid,
        success=True,
        outputs=[],
        duration_seconds=0.0,
    )


def test_run_batch_emits_rsid_start_per_rsid(caplog, tmp_path):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.pipeline.batch")
    fake_client = MagicMock()
    with patch(
        "aa_auto_sdr.pipeline.batch.single.run_single",
        side_effect=lambda **kw: _fake_run_result(kw["rsid"]),
    ):
        result = run_batch(
            client=fake_client,
            rsids=["RS1", "RS2", "RS3"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime.now(UTC),
            tool_version="1.4.0",
        )
    starts = _records_with_event(caplog, "rsid_start")
    assert len(starts) == 3
    assert {r.rsid for r in starts} == {"RS1", "RS2", "RS3"}
    # Every record carries batch_id and it matches the BatchResult field.
    assert all(r.batch_id == result.batch_id for r in starts)


def test_run_batch_emits_rsid_complete_with_duration_and_count(caplog, tmp_path):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.pipeline.batch")
    fake_client = MagicMock()
    fake_with_outputs = RunResult(
        rsid="RS1",
        success=True,
        outputs=[Path("/tmp/a.json"), Path("/tmp/b.csv")],
        duration_seconds=0.0,
    )
    with patch(
        "aa_auto_sdr.pipeline.batch.single.run_single",
        return_value=fake_with_outputs,
    ):
        run_batch(
            client=fake_client,
            rsids=["RS1"],
            formats=["json", "csv"],
            output_dir=tmp_path,
            captured_at=datetime.now(UTC),
            tool_version="1.4.0",
        )
    completes = _records_with_event(caplog, "rsid_complete")
    assert len(completes) == 1
    rec = completes[0]
    assert rec.rsid == "RS1"
    assert rec.count == 2  # two output files
    assert isinstance(rec.duration_ms, int)
    assert rec.duration_ms >= 0


def test_run_batch_emits_rsid_failure_on_continue_on_error(caplog, tmp_path):
    caplog.set_level(logging.ERROR, logger="aa_auto_sdr.pipeline.batch")
    fake_client = MagicMock()

    def maybe_fail(**kw):
        if kw["rsid"] == "BAD":
            raise ApiError("boom")
        return _fake_run_result(kw["rsid"])

    with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=maybe_fail):
        run_batch(
            client=fake_client,
            rsids=["RS1", "BAD", "RS3"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime.now(UTC),
            tool_version="1.4.0",
        )
    failures = _records_with_event(caplog, "rsid_failure")
    assert len(failures) == 1
    rec = failures[0]
    assert rec.rsid == "BAD"
    assert rec.error_class == "ApiError"
    assert isinstance(rec.exit_code, int)


def test_run_batch_emits_summary_record(caplog, tmp_path):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.pipeline.batch")
    fake_client = MagicMock()

    def maybe_fail(**kw):
        if kw["rsid"] == "BAD":
            raise ApiError("boom")
        return _fake_run_result(kw["rsid"])

    with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=maybe_fail):
        result = run_batch(
            client=fake_client,
            rsids=["RS1", "BAD", "RS3"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime.now(UTC),
            tool_version="1.4.0",
        )
    # Summary record is the last INFO line emitted from this module.
    info_recs = [r for r in caplog.records if r.levelno == logging.INFO]
    summary = info_recs[-1]
    assert summary.batch_id == result.batch_id
    assert summary.count == 2  # successes
    assert summary.count_failed == 1
    assert isinstance(summary.duration_ms, int)


def test_run_batch_does_not_emit_run_start_or_run_complete(caplog, tmp_path):
    """De-dup rule (spec §6.5): cli/main.run owns run_start/run_complete.
    run_batch must never emit them, even when invoked directly."""
    caplog.set_level(logging.DEBUG)
    fake_client = MagicMock()
    with patch(
        "aa_auto_sdr.pipeline.batch.single.run_single",
        side_effect=lambda **kw: _fake_run_result(kw["rsid"]),
    ):
        run_batch(
            client=fake_client,
            rsids=["RS1"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime.now(UTC),
            tool_version="1.4.0",
        )
    assert _records_with_event(caplog, "run_start") == []
    assert _records_with_event(caplog, "run_complete") == []
