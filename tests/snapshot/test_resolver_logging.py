"""v1.5 — resolver.resolve_snapshot emits 2 DEBUG (entry + success) and 1 ERROR.

Test discipline (per spec §8): assert event-prefix substring + level +
extras presence; never full message wording. The hermetic autouse
fixture attaches caplog's handler directly to the ``aa_auto_sdr``
package logger and restores prior handler state on teardown."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.snapshot.resolver import resolve_snapshot


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


def _write_snapshot(path: Path, rsid: str = "RS1") -> None:
    """Write a valid snapshot envelope (shape matches existing test_resolver.py)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aa-sdr-snapshot/v1",
                "rsid": rsid,
                "captured_at": "2026-04-26T17:29:01+00:00",
                "tool_version": "1.5.0",
                "components": {
                    "report_suite": {"rsid": rsid, "name": rsid},
                    "dimensions": [],
                    "metrics": [],
                    "segments": [],
                    "calculated_metrics": [],
                    "virtual_report_suites": [],
                    "classifications": [],
                },
            },
            sort_keys=True,
        )
    )


def test_resolve_snapshot_happy_path_emits_two_debug(caplog, tmp_path: Path):
    snap = tmp_path / "snap.json"
    _write_snapshot(snap, "RS1")
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.snapshot.resolver")
    resolve_snapshot(str(snap), profile_snapshot_dir=None, repo_root=None)
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.name == "aa_auto_sdr.snapshot.resolver"]
    assert len(debugs) == 2  # entry + success
    # Both records carry snapshot_spec
    for rec in debugs:
        assert isinstance(rec.snapshot_spec, str)
        assert rec.snapshot_spec == str(snap)
    # Success record carries output_path
    assert hasattr(debugs[1], "output_path")
    assert isinstance(debugs[1].output_path, str)
    assert debugs[1].output_path == str(snap)


def test_resolve_snapshot_failure_emits_error_with_extras(caplog, tmp_path: Path):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.snapshot.resolver")
    bad_token = "does-not-exist@latest"
    with pytest.raises(SnapshotResolveError):
        resolve_snapshot(
            bad_token,
            profile_snapshot_dir=tmp_path,
            repo_root=None,
        )
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.name == "aa_auto_sdr.snapshot.resolver"]
    assert len(errors) == 1
    rec = errors[0]
    assert rec.snapshot_spec == bad_token
    assert rec.error_class == "SnapshotResolveError"


def test_resolve_snapshot_path_not_found_also_emits_error(caplog, tmp_path: Path):
    """Non-existent file path token should also emit ERROR with extras."""
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.snapshot.resolver")
    bad_path = str(tmp_path / "missing.json")
    with pytest.raises(SnapshotResolveError):
        resolve_snapshot(bad_path, profile_snapshot_dir=None, repo_root=None)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.name == "aa_auto_sdr.snapshot.resolver"]
    assert len(errors) == 1
    assert errors[0].snapshot_spec == bad_path
    assert errors[0].error_class == "SnapshotResolveError"
