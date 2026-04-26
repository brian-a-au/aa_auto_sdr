"""generate command: builds AaClient from credentials, runs single pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import generate as cmd

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _build_handle(raw: dict) -> MagicMock:
    import pandas as pd  # local import keeps file linter quiet

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return handle


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_writes_excel_default(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 0
    assert (tmp_path / "demo.prod.xlsx").exists()


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_returns_output_error_when_format_writer_unavailable(
    mock_client_cls, env_creds, tmp_path: Path
) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="data", profile=None)
    # data alias = csv + json; v0.1 only ships json (csv arrives in v0.3)
    # so this run should report a missing-writer error (exit 15) rather than crash
    assert rc == 15


def test_generate_returns_config_error_when_no_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Hermetic test: chdir to tmp_path so credentials.resolve doesn't pick up
    the user's real config.json from the repo root."""
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 10
