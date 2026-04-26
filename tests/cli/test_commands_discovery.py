"""Discovery command handlers: --list-reportsuites, --list-virtual-reportsuites."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@patch("aa_auto_sdr.cli.commands.discovery.AaClient")
def test_list_reportsuites_default_table_to_stdout(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import discovery as cmd

    monkeypatch.chdir(tmp_path)  # avoid picking up real config.json
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "abc.prod", "name": "Production"},
            {"rsid": "abc.dev", "name": "Development"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_reportsuites(
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "abc.prod" in out
    assert "abc.dev" in out


@patch("aa_auto_sdr.cli.commands.discovery.AaClient")
def test_list_reportsuites_json_format(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import discovery as cmd

    monkeypatch.chdir(tmp_path)
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "abc.prod", "name": "Production"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_reportsuites(
        profile=None,
        format_name="json",
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed[0]["rsid"] == "abc.prod"


@patch("aa_auto_sdr.cli.commands.discovery.AaClient")
def test_list_reportsuites_filter_applied(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import discovery as cmd

    monkeypatch.chdir(tmp_path)
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "abc.prod", "name": "Production"},
            {"rsid": "abc.dev", "name": "Development"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_reportsuites(
        profile=None,
        format_name="json",
        output=None,
        name_filter="prod",
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert len(parsed) == 1
    assert parsed[0]["rsid"] == "abc.prod"


def test_list_reportsuites_no_creds_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands import discovery as cmd

    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)

    rc = cmd.run_list_reportsuites(
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.discovery.AaClient")
def test_list_virtual_reportsuites_default_table_to_stdout(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import discovery as cmd

    monkeypatch.chdir(tmp_path)
    handle = MagicMock()
    handle.getVirtualReportSuites.return_value = _df(
        [
            {"id": "vrs_1", "name": "EU Only", "parentRsid": "abc.prod"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_virtual_reportsuites(
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "vrs_1" in out


@patch("aa_auto_sdr.cli.commands.discovery.AaClient")
def test_list_reportsuites_invalid_sort_returns_2(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import discovery as cmd

    monkeypatch.chdir(tmp_path)
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "abc.prod", "name": "Production"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_reportsuites(
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field="invalid_field",
        limit=None,
    )
    assert rc == 2  # usage error
