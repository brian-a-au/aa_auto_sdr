"""End-to-end test of v1.2 subsystems against fixture data."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _build_handle(raw: dict) -> MagicMock:
    import pandas as pd

    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame([raw["report_suite"]])
    handle.getDimensions.return_value = pd.DataFrame(raw["dimensions"])
    handle.getMetrics.return_value = pd.DataFrame(raw["metrics"])
    handle.getSegments.return_value = pd.DataFrame(raw["segments"])
    handle.getCalculatedMetrics.return_value = pd.DataFrame(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = pd.DataFrame(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = pd.DataFrame(raw["classification_datasets"])
    return handle


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_v1_2_dry_run_then_metrics_only(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Dry-run preview then real generate with --metrics-only — end-to-end."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")

    from aa_auto_sdr.cli.commands.generate import run

    rc = run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        dry_run=True,
    )
    assert rc == 0
    assert not (tmp_path / "demo.prod.json").exists()

    rc = run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        metrics_only=True,
    )
    assert rc == 0
    assert (tmp_path / "demo.prod.json").exists()
    payload = json.loads((tmp_path / "demo.prod.json").read_text())
    # Filtered components are empty arrays
    assert payload["dimensions"] == []
    assert len(payload["metrics"]) > 0


def test_v1_2_warn_threshold_triggers(tmp_path: Path) -> None:
    """End-to-end: a real diff with warn-threshold → exit 3 (WARN)."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"

    def _env(metrics: list[dict]) -> dict:
        return {
            "schema": "aa-sdr-snapshot/v1",
            "rsid": "RS1",
            "captured_at": "2026-04-26T10:00:00+00:00",
            "tool_version": "1.2.0",
            "components": {
                "report_suite": {
                    "rsid": "RS1",
                    "name": "RS1",
                    "timezone": "UTC",
                    "currency": "USD",
                    "parent_rsid": None,
                },
                "dimensions": [],
                "metrics": metrics,
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
            },
        }

    a.write_text(json.dumps(_env([{"id": f"m{i}", "name": f"M{i}"} for i in range(2)])))
    b.write_text(json.dumps(_env([{"id": f"m{i}", "name": f"M{i}"} for i in range(5)])))

    from aa_auto_sdr.cli.commands.diff import run

    rc = run(
        a=str(a),
        b=str(b),
        format_name="json",
        output=None,
        profile=None,
        side_by_side=False,
        summary=False,
        ignore_fields=frozenset(),
        quiet=False,
        labels=None,
        reverse=False,
        changes_only=False,
        show_only=frozenset(),
        max_issues=None,
        warn_threshold=3,
    )
    assert rc == 3  # WARN
