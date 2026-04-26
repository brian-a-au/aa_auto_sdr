"""End-to-end CLI dispatch — covers the routing decisions in cli/main.run."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.main import run

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def test_no_args_returns_usage_error(capsys) -> None:
    rc = run([])
    assert rc == 2
    err = capsys.readouterr().err + capsys.readouterr().out
    assert "rsid" in err.lower() or "usage" in err.lower()


def test_show_config_with_no_creds_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = run(["--show-config"])
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_rsid_runs_generate(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import pandas as pd

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")

    rc = run(["demo.prod", "--format", "json", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "demo.prod.json").exists()
