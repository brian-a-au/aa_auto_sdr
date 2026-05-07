"""v1.5 — comparator.compare emits one DEBUG record.

Test discipline (per spec §8): assert level + extras presence; never
full message wording. The hermetic autouse fixture attaches caplog's
handler directly to the ``aa_auto_sdr`` package logger and restores
prior handler state on teardown so records survive any
``setup_logging`` reset and don't leak across tests/files."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from aa_auto_sdr.snapshot.comparator import compare


@pytest.fixture(autouse=True)
def _attach_caplog_to_package_logger(caplog):
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


def _envelope(rsid: str = "RS1") -> dict[str, Any]:
    """Minimal valid envelope shape (per existing test_comparator.py)."""
    return {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": rsid,
        "captured_at": "2026-04-26T17:29:01+00:00",
        "tool_version": "1.5.0",
        "components": {
            "report_suite": {
                "rsid": rsid,
                "name": rsid,
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }


def test_compare_emits_debug_with_required_extras(caplog):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.snapshot.comparator")
    a = _envelope("RS1")
    b = _envelope("RS1")
    compare(a, b)
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.name == "aa_auto_sdr.snapshot.comparator"]
    assert len(debugs) == 1
    rec = debugs[0]
    assert rec.rsid == "RS1"
    assert isinstance(rec.count, int)
    assert rec.count == 0
    assert isinstance(rec.duration_ms, int)


def test_compare_counts_added_removed_modified(caplog):
    """Total changes count should sum added + removed + modified across all components."""
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.snapshot.comparator")

    def _dim(id: str, name: str, **extra) -> dict:
        return {
            "id": id,
            "name": name,
            "type": "string",
            "category": "Custom",
            "parent": "",
            "pathable": False,
            "description": None,
            "tags": [],
            "extra": {},
            **extra,
        }

    a = _envelope("RS1")
    a["components"]["dimensions"] = [_dim("evar1", "User ID")]
    b = _envelope("RS1")
    b["components"]["dimensions"] = [_dim("evar2", "Session ID")]
    compare(a, b)
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.name == "aa_auto_sdr.snapshot.comparator"]
    assert len(debugs) == 1
    # 1 added (evar2) + 1 removed (evar1) + 0 modified = 2
    assert debugs[0].count == 2
