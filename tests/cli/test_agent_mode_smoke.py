"""End-to-end agent-mode smoke tests (mocked SDK). Spec §7."""

from __future__ import annotations

import json
import logging

import pytest


@pytest.fixture(autouse=True)
def _teardown_logging():
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


def test_diff_under_agent_mode_emits_json_to_stdout(tmp_path, monkeypatch, capsys):
    """`--diff <a> <b> --agent-mode` emits DiffReport JSON on stdout."""
    monkeypatch.chdir(tmp_path)

    # Prepare two minimal snapshot files (must match aa-sdr-snapshot/v1 schema)
    snap_a = tmp_path / "a.json"
    snap_b = tmp_path / "b.json"
    base_payload = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "RS1",
        "captured_at": "2026-05-07T00:00:00Z",
        "tool_version": "1.6.0",
        "components": {
            "report_suite": {
                "rsid": "RS1",
                "name": "RS1",
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
    snap_a.write_text(json.dumps(base_payload))
    snap_b.write_text(json.dumps({**base_payload, "captured_at": "2026-05-07T01:00:00Z"}))

    from aa_auto_sdr.cli.main import run

    exit_code = run(["--diff", str(snap_a), str(snap_b), "--agent-mode"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert "components" in payload  # DiffReport JSON shape
