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


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_json_to_file(
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
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        run_summary_json=str(summary_path),
    )
    assert rc == ExitCode.OK.value
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text())
    assert payload["tool_version"]
    assert payload["rsids"][0]["rsid"] == "demo.prod"
    assert payload["rsids"][0]["succeeded"] is True
    assert payload["timings"] == []  # show_timings was unset


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_json_to_stdout(
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
        run_summary_json="-",
    )
    assert rc == ExitCode.OK.value
    out = capsys.readouterr().out
    payload = json.loads(out.strip().splitlines()[-1])  # last line is the summary
    assert payload["rsids"][0]["rsid"] == "demo.prod"


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_json_includes_timings_when_show_timings(
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
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=True,
        run_summary_json=str(summary_path),
    )
    assert rc == ExitCode.OK.value
    payload = json.loads(summary_path.read_text())
    assert payload["timings"], "expected non-empty timings list when --show-timings is set"
    # Each entry is [label, seconds].
    assert all(len(t) == 2 and isinstance(t[0], str) for t in payload["timings"])


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_json_with_failure(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """When the build raises, the summary records succeeded=False + error message."""
    from aa_auto_sdr.core.exceptions import ApiError

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )
    summary_path = tmp_path / "summary.json"
    with patch(
        "aa_auto_sdr.pipeline.single.build_sdr",
        side_effect=ApiError("simulated API outage"),
    ):
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",  # file-output path
            profile=None,
            run_summary_json=str(summary_path),
        )
    assert rc == ExitCode.API.value
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text())
    assert payload["rsids"][0]["succeeded"] is False
    assert "simulated API outage" in (payload["rsids"][0]["error"] or "")


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_json_pipe_path_with_apierror(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """Pipe path (output_dir = Path('-'), format=json) failure: build_sdr raises
    ApiError, the summary still records succeeded=False to the file path."""
    from aa_auto_sdr.core.exceptions import ApiError

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    summary_path = tmp_path / "summary.json"
    with patch(
        "aa_auto_sdr.cli.commands.generate.build_sdr",
        side_effect=ApiError("pipe simulated"),
    ):
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),  # pipe path
            format_name="json",
            profile=None,
            run_summary_json=str(summary_path),
        )
    assert rc == ExitCode.API.value
    payload = json.loads(summary_path.read_text())
    assert payload["rsids"][0]["succeeded"] is False
    assert "pipe simulated" in (payload["rsids"][0]["error"] or "")


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_json_file_path_with_output_error(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """File-output path + OutputError from single.run_single → summary records
    failure with succeeded=False."""
    from aa_auto_sdr.core.exceptions import OutputError

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    summary_path = tmp_path / "summary.json"
    with patch(
        "aa_auto_sdr.pipeline.single.run_single",
        side_effect=OutputError("disk full"),
    ):
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            run_summary_json=str(summary_path),
        )
    assert rc == ExitCode.OUTPUT.value
    payload = json.loads(summary_path.read_text())
    assert payload["rsids"][0]["succeeded"] is False
    assert "disk full" in (payload["rsids"][0]["error"] or "")
