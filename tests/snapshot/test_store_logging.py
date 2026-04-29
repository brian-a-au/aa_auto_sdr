"""v1.4 — assert snapshot/store.py emits documented records.

Test discipline (per spec §8): assert event-prefix substring + level +
extras presence; never full message wording. The hermetic autouse fixture
attaches caplog's handler directly to the ``aa_auto_sdr`` package logger
and restores prior handler state on teardown so records survive any
``setup_logging`` reset and don't leak across tests/files."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.snapshot.store import (
    prune_snapshots,
    save_snapshot,
)


@pytest.fixture(autouse=True)
def _attach_caplog_to_package_logger(caplog):
    """Attach caplog's handler to the aa_auto_sdr package logger so records
    survive any setup_logging root-handler reset, then restore on teardown.

    We also disable propagation for the duration of the test: without
    setup_logging in the picture, records would otherwise reach both the
    package-attached handler and pytest's default root handler, producing
    duplicate captures."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    saved_propagate = pkg.propagate
    pkg.addHandler(caplog.handler)
    pkg.setLevel(logging.DEBUG)
    pkg.propagate = False
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)
        pkg.propagate = saved_propagate


def _records_with_event(caplog, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if event in r.getMessage()]


def _fake_doc(rsid: str = "RS1"):
    """Build the smallest valid SdrDocument that document_to_envelope accepts.
    Imported lazily to avoid weighing every test file with sdr.* deps."""
    from aa_auto_sdr.api.models import ReportSuite
    from aa_auto_sdr.sdr.document import SdrDocument

    return SdrDocument(
        report_suite=ReportSuite(
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
        captured_at=datetime(2026, 4, 28, 0, 0, 0, tzinfo=UTC),
        tool_version="1.4.0",
    )


def test_save_snapshot_emits_info_with_required_extras(caplog, tmp_path):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.snapshot.store")
    doc = _fake_doc("RS1")
    save_snapshot(doc, snapshot_dir=tmp_path)
    saves = _records_with_event(caplog, "snapshot_save")
    assert len(saves) == 1
    rec = saves[0]
    assert rec.levelno == logging.INFO
    assert rec.rsid == "RS1"
    assert isinstance(rec.snapshot_id, str)
    assert rec.snapshot_id
    assert isinstance(rec.output_path, str)
    assert rec.output_path.endswith(".json")
    assert isinstance(rec.count, int)
    assert isinstance(rec.duration_ms, int)


def test_prune_snapshots_warning_on_skipped_file(caplog, tmp_path, monkeypatch):
    """When prune iterates and a file raises OSError on unlink, emit a
    WARNING with the path and error_class — don't abort the whole prune."""
    from datetime import timedelta

    caplog.set_level(logging.WARNING, logger="aa_auto_sdr.snapshot.store")
    rs_dir = tmp_path / "RS1"
    rs_dir.mkdir()
    (rs_dir / "2026-04-28T00-00-00+00-00.json").write_text('{"x": 1}')

    from aa_auto_sdr.snapshot.retention import RetentionPolicy

    def boom(self, *a, **kw):
        raise OSError("disk gremlin")

    monkeypatch.setattr(Path, "unlink", boom)
    # Use keep_since with `now` far enough in the future that the file
    # is older than the cutoff and gets selected for deletion.
    policy = RetentionPolicy(keep_last=None, keep_since=timedelta(days=1))
    later = datetime(2030, 1, 1, tzinfo=UTC)
    deleted = prune_snapshots(tmp_path, policy, now=later)
    # Function does not raise; the file is skipped, not deleted.
    assert deleted == []
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1
    rec = warns[0]
    assert rec.error_class == "OSError"
    assert "RS1" in rec.output_path
