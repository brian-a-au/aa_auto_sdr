"""v1.2.1 batch: --show-timings wiring (covers post-auth error-path emit branches)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from aa_auto_sdr.cli.commands import batch as cmd
from aa_auto_sdr.core import timings
from aa_auto_sdr.core.exit_codes import ExitCode

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _build_handle(raw: dict) -> MagicMock:
    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame([raw["report_suite"]])
    handle.getDimensions.return_value = pd.DataFrame(raw["dimensions"])
    handle.getMetrics.return_value = pd.DataFrame(raw["metrics"])
    handle.getSegments.return_value = pd.DataFrame(raw["segments"])
    handle.getCalculatedMetrics.return_value = pd.DataFrame(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = pd.DataFrame(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = pd.DataFrame(raw["classification_datasets"])
    return handle


@pytest.fixture(autouse=True)
def _reset_timings() -> None:
    timings.disable()
    timings.clear()
    yield
    timings.disable()
    timings.clear()


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_show_timings_emits_block_on_auth_error(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When batch auth fails AND --show-timings is set, the timings block emits."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
    rc = cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=True,
    )
    assert rc == ExitCode.AUTH.value
    err = capsys.readouterr().err
    assert "Timings:" in err
    assert "auth" in err  # the Timer("auth") row should appear even on AuthError


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_run_summary_json_to_file(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    summary_path = tmp_path / "summary.json"
    rc = cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        run_summary_json=str(summary_path),
    )
    assert rc == ExitCode.OK.value
    payload = json.loads(summary_path.read_text())
    assert payload["rsids"][0]["rsid"] == "demo.prod"
    assert payload["rsids"][0]["succeeded"] is True


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_show_timings_emits_block(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=True,
    )
    assert rc == ExitCode.OK.value
    err = capsys.readouterr().err
    assert "Timings:" in err


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_run_summary_json_with_failure(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """When the per-RSID build raises, the batch summary records succeeded=False
    + the error message under rsids[0].error."""
    from aa_auto_sdr.core.exceptions import ApiError

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    summary_path = tmp_path / "summary.json"
    with patch(
        "aa_auto_sdr.pipeline.single.build_sdr",
        side_effect=ApiError("simulated outage"),
    ):
        rc = cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            run_summary_json=str(summary_path),
        )
    # All-failed batch returns the last failure's exit code (API)
    assert rc == ExitCode.API.value
    payload = json.loads(summary_path.read_text())
    assert payload["rsids"][0]["succeeded"] is False
    assert "simulated outage" in (payload["rsids"][0]["error"] or "")
