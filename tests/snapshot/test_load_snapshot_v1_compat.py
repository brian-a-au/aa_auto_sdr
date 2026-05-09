"""load_snapshot defaults v1-envelope new keys to empty — spec §4.6."""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.snapshot.store import load_snapshot


def _write_v1_envelope(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aa-sdr-snapshot/v1",
                "rsid": "rs1",
                "captured_at": "2026-04-26T17:29:01+00:00",
                "tool_version": "1.0.0",
                "components": {
                    "report_suite": {
                        "rsid": "rs1",
                        "name": "rs1",
                        "timezone": None,
                        "currency": None,
                        "parent_rsid": None,
                    },
                    "dimensions": [],
                    "metrics": [],
                    "segments": [],
                    "calculated_metrics": [],
                    "virtual_report_suites": [],
                    "classifications": [],
                },
            },
        ),
    )
    return path


def _write_v2_envelope(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aa-sdr-snapshot/v2",
                "rsid": "rs1",
                "captured_at": "2026-05-08T10:00:00+00:00",
                "tool_version": "1.7.1",
                "degraded_components": ["classifications"],
                "partial_components": {"virtual_report_suites": "minimal"},
                "components": {
                    "report_suite": {
                        "rsid": "rs1",
                        "name": "rs1",
                        "timezone": None,
                        "currency": None,
                        "parent_rsid": None,
                    },
                    "dimensions": [],
                    "metrics": [],
                    "segments": [],
                    "calculated_metrics": [],
                    "virtual_report_suites": [],
                    "classifications": [],
                },
            },
        ),
    )
    return path


def test_load_v1_envelope_defaults_new_keys_to_empty(tmp_path: Path) -> None:
    p = _write_v1_envelope(tmp_path / "rs1" / "snap.json")
    env = load_snapshot(p)
    assert env["degraded_components"] == []
    assert env["partial_components"] == {}


def test_load_v2_envelope_passes_through_new_keys(tmp_path: Path) -> None:
    p = _write_v2_envelope(tmp_path / "rs1" / "snap.json")
    env = load_snapshot(p)
    assert env["degraded_components"] == ["classifications"]
    assert env["partial_components"] == {"virtual_report_suites": "minimal"}


def test_load_snapshot_does_not_mutate_disk(tmp_path: Path) -> None:
    """Defaulting is in-memory only; the file on disk stays v1."""
    p = _write_v1_envelope(tmp_path / "rs1" / "snap.json")
    load_snapshot(p)
    raw = json.loads(p.read_text())
    assert raw["schema"] == "aa-sdr-snapshot/v1"
    assert "degraded_components" not in raw
    assert "partial_components" not in raw
