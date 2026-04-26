"""Inspect command handlers: --list-metrics/dimensions/segments/calculated-metrics
/classification-datasets, --describe-reportsuite."""

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


def _mock_handle_with_one_rs() -> MagicMock:
    """Mock handle wired up so resolve_rsid + per-component fetches succeed for
    rsid 'demo.prod' / name 'Demo'."""
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "demo.prod", "name": "Demo", "currency": "USD"},
        ]
    )
    handle.getDimensions.return_value = _df(
        [
            {
                "id": "variables/evar1",
                "name": "User ID",
                "type": "string",
                "category": "Conversion",
                "parent": "",
                "pathable": False,
                "description": "auth user",
                "tags": [],
            },
            {
                "id": "variables/evar2",
                "name": "Page Type",
                "type": "string",
                "category": "Content",
                "parent": "",
                "pathable": True,
                "description": None,
                "tags": [],
            },
        ]
    )
    handle.getMetrics.return_value = _df(
        [
            {
                "id": "metrics/pageviews",
                "name": "Page Views",
                "type": "int",
                "category": "Traffic",
                "precision": 0,
                "segmentable": True,
                "description": "Total page views",
                "tags": [],
            },
        ]
    )
    handle.getSegments.return_value = _df(
        [
            {
                "id": "s_111",
                "name": "Mobile",
                "description": "mobile traffic",
                "rsid": "demo.prod",
                "owner": {"id": 42},
                "definition": {"hits": "device=mobile"},
                "compatibility": {},
                "tags": [],
            },
        ]
    )
    handle.getCalculatedMetrics.return_value = _df(
        [
            {
                "id": "cm_1",
                "name": "Conv Rate",
                "description": "ratio",
                "rsid": "demo.prod",
                "owner": {"id": 42},
                "polarity": "positive",
                "precision": 4,
                "type": "decimal",
                "definition": {"func": "divide"},
                "tags": [],
                "categories": [],
            },
        ]
    )
    handle.getVirtualReportSuites.return_value = _df([])
    handle.getClassificationDatasets.return_value = _df(
        [
            {"id": "ds_5", "name": "Campaign Metadata", "rsid": "demo.prod"},
        ]
    )
    return handle


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_table_to_stdout(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_metrics(
        identifier="demo.prod",
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
    assert "metrics/pageviews" in out
    assert "Page Views" in out


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_resolves_name_to_rsid(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    # Pass the name "Demo" instead of the rsid
    rc = cmd.run_list_metrics(
        identifier="Demo",
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
    assert "metrics/pageviews" in out


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_multimatch_adds_rsid_column(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    # Override getReportSuites with two suites sharing a name
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "demo.prod", "name": "Shared"},
            {"rsid": "demo.dev", "name": "Shared"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_metrics(
        identifier="Shared",
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
    # Each record gets an "rsid" column when multi-match
    assert all("rsid" in r for r in parsed)
    rsids = {r["rsid"] for r in parsed}
    assert rsids == {"demo.prod", "demo.dev"}


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_no_match_returns_13(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_metrics(
        identifier="nonexistent",
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 13


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_dimensions_table_to_stdout(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_dimensions(
        identifier="demo.prod",
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
    assert "variables/evar1" in out
    assert "User ID" in out


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_segments_table_to_stdout(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_segments(
        identifier="demo.prod",
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
    assert "s_111" in out
    assert "Mobile" in out


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_calculated_metrics_table_to_stdout(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_calculated_metrics(
        identifier="demo.prod",
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
    assert "cm_1" in out
    assert "Conv Rate" in out


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_classification_datasets_table_to_stdout(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_list_classification_datasets(
        identifier="demo.prod",
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
    assert "ds_5" in out
    assert "Campaign Metadata" in out


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_reportsuite_single_row(mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run_describe_reportsuite(
        identifier="demo.prod",
        profile=None,
        format_name="json",
        output=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert len(parsed) == 1
    assert parsed[0]["rsid"] == "demo.prod"
    assert parsed[0]["dimensions"] == 2
    assert parsed[0]["metrics"] == 1
    assert parsed[0]["segments"] == 1
    assert parsed[0]["calculated_metrics"] == 1
    assert parsed[0]["virtual_report_suites"] == 0
    assert parsed[0]["classifications"] == 1


# ---------------------------------------------------------------------------
# Error-path tests (v0.9 coverage gate raise to 90%)
# ---------------------------------------------------------------------------


def test_list_metrics_no_creds_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run_list_metrics(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_auth_error_returns_11(mock_client_cls, env_creds, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("nope")
    rc = cmd.run_list_metrics(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 11


def test_describe_reportsuite_no_creds_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run_describe_reportsuite(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
    )
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_reportsuite_auth_error_returns_11(mock_client_cls, env_creds) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("nope")
    rc = cmd.run_describe_reportsuite(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
    )
    assert rc == 11


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_api_error_returns_12(mock_client_cls, env_creds, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import ApiError

    handle = MagicMock()
    handle.getReportSuites.side_effect = ApiError("rate")
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    rc = cmd.run_list_metrics(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=None,
    )
    assert rc == 12


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_reportsuite_unknown_returns_13(mock_client_cls, env_creds) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame(
        [{"rsid": "demo.prod", "name": "Demo Production", "timezone": "UTC", "currency": "USD", "parentRsid": ""}]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    rc = cmd.run_describe_reportsuite(
        identifier="never-exists",
        profile=None,
        format_name=None,
        output=None,
    )
    assert rc == 13
