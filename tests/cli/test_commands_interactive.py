"""--interactive handler: list RSes, prompt for selection, emit chosen RSIDs."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import interactive as cmd
from aa_auto_sdr.core.exit_codes import ExitCode

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _build_handle(raw: dict) -> MagicMock:
    import pandas as pd

    handle = MagicMock()
    # Two suites available so we can test selection.
    rs2 = {**raw["report_suite"], "rsid": "demo.staging", "name": "Demo Staging"}
    handle.getReportSuites.return_value = pd.DataFrame([raw["report_suite"], rs2])
    return handle


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


@patch("aa_auto_sdr.cli.commands.interactive.AaClient")
def test_select_by_index(
    mock_client_cls,
    env_creds,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    monkeypatch.setattr("builtins.input", lambda _: "1")
    rc = cmd.run(profile=None)
    assert rc == ExitCode.OK.value
    out = capsys.readouterr().out
    # Final line is the chosen RSID(s)
    assert "demo.prod" in out


@patch("aa_auto_sdr.cli.commands.interactive.AaClient")
def test_select_all(
    mock_client_cls,
    env_creds,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    monkeypatch.setattr("builtins.input", lambda _: "all")
    rc = cmd.run(profile=None)
    assert rc == ExitCode.OK.value
    out = capsys.readouterr().out
    assert "demo.prod" in out
    assert "demo.staging" in out


@patch("aa_auto_sdr.cli.commands.interactive.AaClient")
def test_invalid_selection(
    mock_client_cls,
    env_creds,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )
    monkeypatch.setattr("builtins.input", lambda _: "999")
    rc = cmd.run(profile=None)
    assert rc == ExitCode.USAGE.value


@patch("aa_auto_sdr.cli.commands.interactive.AaClient")
def test_keyboard_interrupt_returns_130(
    mock_client_cls,
    env_creds,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=_build_handle(raw),
        company_id="testco",
    )

    def _interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _interrupt)
    rc = cmd.run(profile=None)
    assert rc == 130


def test_missing_creds_returns_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(profile=None)
    assert rc == ExitCode.CONFIG.value
