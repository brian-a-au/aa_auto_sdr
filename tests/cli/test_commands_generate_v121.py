"""v1.2.1 generate: --show-timings + --run-summary-json wiring."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from aa_auto_sdr.cli.commands import generate as cmd
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


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_show_timings_emits_block(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When --show-timings is set, a per-stage timings block prints to stderr."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=True,
    )
    assert rc == ExitCode.OK.value
    err = capsys.readouterr().err
    assert "Timings:" in err
    assert "Total" in err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_no_timings_block_when_flag_unset(
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
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=False,
    )
    assert rc == ExitCode.OK.value
    err = capsys.readouterr().err
    assert "Timings:" not in err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_timings_with_dry_run_still_emits(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run still does auth + resolve; those stages should appear."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        dry_run=True,
        show_timings=True,
    )
    assert rc == ExitCode.OK.value
    err = capsys.readouterr().err
    assert "Timings:" in err
    assert "auth" in err
    assert "resolve" in err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_show_timings_emits_block_on_auth_error(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When auth fails AND --show-timings is set, the timings block (with the
    auth row) still emits before the AUTH return."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=True,
    )
    assert rc == ExitCode.AUTH.value
    err = capsys.readouterr().err
    assert "Timings:" in err
    assert "auth" in err
