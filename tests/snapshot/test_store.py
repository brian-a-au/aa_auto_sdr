"""snapshot/store.py — save_snapshot / load_snapshot / filename sanitization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.api import models as api_models
from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot.store import (
    captured_at_to_filename,
    load_snapshot,
    save_snapshot,
    snapshot_path,
)


def _stub_doc(rsid: str = "demo.prod") -> SdrDocument:
    rs = api_models.ReportSuite(
        rsid=rsid,
        name="Demo Production",
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )
    return SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 26, 17, 29, 1, tzinfo=UTC),
        tool_version="0.7.0",
    )


def test_captured_at_to_filename_replaces_colons_with_hyphens() -> None:
    ts = "2026-04-26T17:29:01+00:00"
    assert captured_at_to_filename(ts) == "2026-04-26T17-29-01+00-00.json"


def test_snapshot_path_has_profile_rsid_layout(tmp_path: Path) -> None:
    p = snapshot_path(
        snapshot_dir=tmp_path,
        rsid="demo.prod",
        captured_at_iso="2026-04-26T17:29:01+00:00",
    )
    # snapshot_dir is the per-profile snapshots root
    assert p == tmp_path / "demo.prod" / "2026-04-26T17-29-01+00-00.json"


def test_save_snapshot_writes_envelope_with_sorted_keys(tmp_path: Path) -> None:
    out = save_snapshot(_stub_doc(), snapshot_dir=tmp_path)
    assert out.exists()
    text = out.read_text()
    # Envelope keys must appear in sorted order: captured_at, components, rsid, schema, tool_version
    assert text.find('"captured_at"') < text.find('"components"')
    assert text.find('"components"') < text.find('"rsid"')
    assert text.find('"rsid"') < text.find('"schema"')
    assert text.find('"schema"') < text.find('"tool_version"')


def test_save_snapshot_returns_path_under_rsid_dir(tmp_path: Path) -> None:
    out = save_snapshot(_stub_doc(rsid="demo.staging"), snapshot_dir=tmp_path)
    assert out.parent == tmp_path / "demo.staging"
    assert out.name == "2026-04-26T17-29-01+00-00.json"


def test_save_snapshot_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested"
    out = save_snapshot(_stub_doc(), snapshot_dir=target)
    assert out.exists()
    assert out.parent.parent == target


def test_load_snapshot_round_trips(tmp_path: Path) -> None:
    out = save_snapshot(_stub_doc(), snapshot_dir=tmp_path)
    env = load_snapshot(out)
    assert env["schema"] == "aa-sdr-snapshot/v1"
    assert env["rsid"] == "demo.prod"
    assert env["captured_at"] == "2026-04-26T17:29:01+00:00"


def test_load_snapshot_validates_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "aa-sdr-snapshot/v999", "rsid": "x"}))
    with pytest.raises(SnapshotSchemaError):
        load_snapshot(bad)


def test_save_snapshot_overwrites_existing_file_at_same_timestamp(tmp_path: Path) -> None:
    """Re-saving the same captured_at overwrites (atomic write)."""
    save_snapshot(_stub_doc(), snapshot_dir=tmp_path)
    out = save_snapshot(_stub_doc(), snapshot_dir=tmp_path)
    assert out.exists()


def test_save_snapshot_wraps_oserror_in_output_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec §3: snapshot-write failures must raise OutputError so run_batch can fold
    them into BatchFailure instead of aborting the whole batch."""
    from aa_auto_sdr.core.exceptions import OutputError
    from aa_auto_sdr.snapshot import store

    def _boom(*_a, **_kw):
        raise PermissionError("disk on fire")

    monkeypatch.setattr(store, "write_json", _boom)
    with pytest.raises(OutputError, match="snapshot write failed"):
        save_snapshot(_stub_doc(), snapshot_dir=tmp_path)
