"""--stats handler: quick component counts without full SDR build."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import stats as cmd
from aa_auto_sdr.core.exit_codes import ExitCode

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


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


@patch("aa_auto_sdr.cli.commands.stats.AaClient")
def test_stats_one_rsid_table(
    mock_client_cls,
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(rsids=["demo.prod"], profile=None, format_name="table")
    assert rc == ExitCode.OK.value
    out = capsys.readouterr().out
    assert "demo.prod" in out
    assert "DIM" in out or "MET" in out


@patch("aa_auto_sdr.cli.commands.stats.AaClient")
def test_stats_one_rsid_json(
    mock_client_cls,
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(rsids=["demo.prod"], profile=None, format_name="json")
    assert rc == ExitCode.OK.value
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert payload[0]["rsid"] == "demo.prod"
    assert "counts" in payload[0]
    assert payload[0]["counts"]["metrics"] >= 0


def test_stats_missing_creds_returns_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(rsids=["demo.prod"], profile=None, format_name="table")
    assert rc == ExitCode.CONFIG.value


@patch("aa_auto_sdr.cli.commands.stats.AaClient")
def test_stats_no_rsids_lists_all_visible(
    mock_client_cls,
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(rsids=[], profile=None, format_name="json")
    assert rc == ExitCode.OK.value
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) >= 1


@patch("aa_auto_sdr.cli.commands.stats.AaClient")
def test_stats_unknown_rsid_returns_not_found(
    mock_client_cls,
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    rc = cmd.run(rsids=["nonexistent.rsid"], profile=None, format_name="table")
    assert rc == ExitCode.NOT_FOUND.value


def test_stats_bad_format_returns_output_error(
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cmd.run(rsids=["demo.prod"], profile=None, format_name="yaml")
    assert rc == ExitCode.OUTPUT.value


@patch("aa_auto_sdr.cli.commands.stats.AaClient")
def test_stats_auth_error_returns_auth_exit(
    mock_client_cls,
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """v1.2 — AuthError from AaClient.from_credentials → exit 11."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
    rc = cmd.run(rsids=["demo.prod"], profile=None, format_name="table")
    assert rc == ExitCode.AUTH.value
    assert "auth error" in capsys.readouterr().out.lower()


@patch("aa_auto_sdr.cli.commands.stats.AaClient")
def test_stats_api_error_on_fetch_returns_api_exit(
    mock_client_cls,
    env_creds,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """v1.2 — ApiError during the per-RSID component count → exit 12."""
    from aa_auto_sdr.core.exceptions import ApiError

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    handle.getDimensions.side_effect = ApiError("rate limit")
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )
    rc = cmd.run(rsids=["demo.prod"], profile=None, format_name="table")
    assert rc == ExitCode.API.value
