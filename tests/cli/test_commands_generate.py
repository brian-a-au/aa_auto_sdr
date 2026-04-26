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
def test_generate_format_data_alias_writes_csv_and_json(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """`data` alias = csv + json. Both writers are present in v0.2; this run
    succeeds and produces both output sets (one csv per component + one json)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="data", profile=None)
    assert rc == 0
    # CSV produces 7 files; JSON produces 1
    csv_files = sorted(p.name for p in tmp_path.glob("demo.prod.*.csv"))
    assert len(csv_files) == 7
    assert (tmp_path / "demo.prod.json").exists()


def test_generate_returns_config_error_when_no_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Hermetic test: chdir to tmp_path so credentials.resolve doesn't pick up
    the user's real config.json from the repo root."""
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_resolves_unique_name_to_rsid(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """User passes a unique name; the canonical RSID is logged and used.
    Output filename keyed off canonical RSID, not the input name."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    # The fixture's report_suite has rsid=demo.prod, name="Demo Production"
    rc = cmd.run(
        rsid="Demo Production",  # name, not rsid
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    # Output filename is keyed off the canonical RSID
    assert (tmp_path / "demo.prod.json").exists()
    captured = capsys.readouterr()
    assert "using report suite: 'Demo Production' (rsid: demo.prod)" in captured.out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_multi_match_by_name_runs_pipeline_per_rsid(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """Two suites share a name. CLI runs the pipeline once per RSID and writes
    distinct output files keyed off each canonical RSID."""
    import pandas as pd

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)

    # Override getReportSuites with two suites sharing a name. Both must point
    # at the same demo.prod-shaped data because all other mocked methods
    # (getDimensions, etc.) ignore rsid in this mock.
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "demo.prod", "name": "Shared Name"},
            {"rsid": "demo.dev", "name": "Shared Name"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="Shared Name",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    # Both output files exist, named after each canonical RSID
    assert (tmp_path / "demo.prod.json").exists()
    assert (tmp_path / "demo.dev.json").exists()

    captured = capsys.readouterr()
    assert "matches 2 report suites" in captured.out
    assert "generating SDR 1/2: demo.prod" in captured.out
    assert "generating SDR 2/2: demo.dev" in captured.out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_json_to_stdout(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """--format json --output - writes JSON to stdout, no 'wrote:' diagnostic."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
    )
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    # JSON SDR doc has report_suite, dimensions, etc.
    assert parsed["report_suite"]["rsid"] == "demo.prod"
    assert "wrote:" not in captured.out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_csv_rejected(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """--format csv --output - rejects (multi-file)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="csv",
        profile=None,
    )
    assert rc == 15


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_excel_rejected(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="excel",
        profile=None,
    )
    assert rc == 15


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_alias_rejected(mock_client_cls, env_creds, tmp_path: Path) -> None:
    """--format all --output - rejects (multi-format)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="all",
        profile=None,
    )
    assert rc == 15


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_snapshot_writes_to_profile_dir(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--snapshot --profile X persists envelope to <home>/.aa/orgs/X/snapshots/<rsid>/<ts>.json."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    profile_dir = fake_home / ".aa" / "orgs" / "prod"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(json.dumps({
        "org_id": "O", "client_id": "C", "secret": "S", "scopes": "X",
    }))

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path / "out",
        format_name="json",
        profile="prod",
        snapshot=True,
    )
    assert rc == 0
    snap_dir = fake_home / ".aa" / "orgs" / "prod" / "snapshots" / "demo.prod"
    assert snap_dir.exists()
    files = list(snap_dir.glob("*.json"))
    assert len(files) == 1


def test_generate_snapshot_without_profile_returns_10(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        snapshot=True,
    )
    assert rc == 10
