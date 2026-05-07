"""v1.5 carry-over #1 — assert exc_text appears at the top level of NDJSON
records when records carry exception info. v1.4's SensitiveDataFilter pre-
formats and redacts the traceback into record.exc_text; v1.5 surfaces it.

This test calls setup_logging(ns) directly and reads the per-run log file
from disk, so caplog is not used. No autouse fixture is needed for THIS
file — but in tests that DO use caplog AND call setup_logging, the
_attach_caplog_to_package_logger fixture from sibling v1.4 logging tests
is required (see plan §"Autouse fixture disambiguation" below)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pytest

from aa_auto_sdr.core.logging import setup_logging


@pytest.fixture(autouse=True)
def _isolate_root_handlers():
    """Snapshot root-logger handler list before each test, restore after.
    This file's test calls setup_logging() which clears and re-installs
    root handlers — without this fixture, handlers leak across tests in
    the same module."""
    root = logging.getLogger()
    saved = root.handlers[:]
    saved_level = root.level
    yield
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)
    for h in saved:
        root.addHandler(h)
    root.setLevel(saved_level)


def _make_ns(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        rsids=[],
        diff=None,
        batch=None,
        list_reportsuites=False,
        list_virtual_reportsuites=False,
        describe_reportsuite=None,
        list_metrics=None,
        list_dimensions=None,
        list_segments=None,
        list_calculated_metrics=None,
        list_classification_datasets=None,
        list_snapshots=False,
        prune_snapshots=False,
        profile_add=None,
        profile_test=None,
        profile_show=None,
        profile_list=False,
        profile_import=None,
        show_config=False,
        config_status=False,
        validate_config=False,
        sample_config=False,
        stats=False,
        interactive=False,
        log_level="INFO",
        log_format="json",
        quiet=False,
    )


def test_exc_text_surfaces_in_ndjson(tmp_path, monkeypatch):
    """A logger.exception(...) call site under --log-format=json produces a
    record where exc_text appears at the top level of the NDJSON object and
    contains the (redacted) traceback."""
    monkeypatch.chdir(tmp_path)
    ns = _make_ns(tmp_path)
    setup_logging(ns)

    logger = logging.getLogger("aa_auto_sdr.tests.exc_text")
    try:
        raise RuntimeError("boom — Bearer abc.def.ghi should be redacted")
    except RuntimeError:
        logger.exception("test traceback emit")

    # Find the per-run log file.
    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, "expected a log file under logs/"
    payload = log_files[-1].read_text()

    # Find the line carrying our message.
    matching = [line for line in payload.splitlines() if "test traceback emit" in line]
    assert matching, "expected the test record to be present"
    record = json.loads(matching[-1])
    assert "exc_text" in record, "exc_text must appear at top level of NDJSON"
    assert "Traceback" in record["exc_text"]
    # v1.4 redaction is intact: bearer token in the exception message is scrubbed.
    assert "abc.def.ghi" not in record["exc_text"]
    assert "Bearer [REDACTED]" in record["exc_text"]
