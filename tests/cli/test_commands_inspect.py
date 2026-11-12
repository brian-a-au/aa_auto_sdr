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


# --- error-path coverage for _list_per_component / run_describe_reportsuite ---


def _raise(exc):
    def _fn(*args, **kwargs):
        raise exc

    return _fn


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_api_error_in_component_fetch_returns_12(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    """resolve succeeds, but the per-component fetch raises ApiError → exit 12."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import ApiError
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    monkeypatch.setattr(fetch, "fetch_metrics", _raise(ApiError("rate limited")))

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
    assert rc == ExitCode.API.value
    assert "api error" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_generic_error_in_component_fetch_returns_1(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    """A non-API AaAutoSdrError from the component fetch → exit 1 (GENERIC)."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import AaAutoSdrError
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    monkeypatch.setattr(fetch, "fetch_metrics", _raise(AaAutoSdrError("unexpected")))

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
    assert rc == ExitCode.GENERIC.value
    assert "error:" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_list_metrics_invalid_limit_returns_usage(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    """apply_filters raises ValueError on a negative --limit → exit 2 (USAGE)."""
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run_list_metrics(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
        name_filter=None,
        name_exclude=None,
        sort_field=None,
        limit=-1,
    )
    assert rc == ExitCode.USAGE.value
    assert "--limit" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_api_error_during_resolve_returns_12(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    """An ApiError from resolve_rsid in describe → exit 12 (API)."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import ApiError
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")
    monkeypatch.setattr(fetch, "resolve_rsid", _raise(ApiError("503")))

    rc = cmd.run_describe_reportsuite(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
    )
    assert rc == ExitCode.API.value
    assert "api error" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_api_error_during_component_fetch_returns_12(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    """resolve succeeds but a per-RSID component fetch raises ApiError → exit 12."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import ApiError
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    monkeypatch.setattr(fetch, "fetch_report_suite", _raise(ApiError("boom")))

    rc = cmd.run_describe_reportsuite(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
    )
    assert rc == ExitCode.API.value


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_generic_error_during_component_fetch_returns_1(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    """A non-API AaAutoSdrError during the per-RSID fetch → exit 1 (GENERIC)."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exceptions import AaAutoSdrError
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    monkeypatch.setattr(fetch, "fetch_dimensions", _raise(AaAutoSdrError("weird")))

    rc = cmd.run_describe_reportsuite(
        identifier="demo.prod",
        profile=None,
        format_name=None,
        output=None,
    )
    assert rc == ExitCode.GENERIC.value


# --- describe reuses the resolve listing for the report suite row ---


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_reportsuite_makes_one_get_report_suites_call(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.cli.commands import inspect as cmd

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run_describe_reportsuite(identifier="Demo", profile=None, format_name="json", output=None)
    assert rc == 0
    assert handle.getReportSuites.call_count == 1
    [record] = json.loads(capsys.readouterr().out)
    assert (record["rsid"], record["name"], record["currency"], record["timezone"]) == (
        "demo.prod",
        "Demo",
        "USD",
        None,
    )


@patch("aa_auto_sdr.cli.commands.inspect.AaClient")
def test_describe_reportsuite_listing_failure_keeps_message_and_exit_code(
    mock_client_cls, env_creds, tmp_path: Path, monkeypatch, capsys
) -> None:
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.resilience import RetryPolicy
    from aa_auto_sdr.cli.commands import inspect as cmd
    from aa_auto_sdr.core.exit_codes import ExitCode

    monkeypatch.chdir(tmp_path)
    handle = _mock_handle_with_one_rs()
    handle.getReportSuites.side_effect = AttributeError("listing exploded")
    mock_client_cls.from_credentials.return_value = AaClient(
        handle=handle, company_id="testco", retry_policy=RetryPolicy(max_retries=0)
    )

    rc = cmd.run_describe_reportsuite(identifier="demo.prod", profile=None, format_name="json", output=None)
    assert rc == ExitCode.API.value
    assert capsys.readouterr().err == "api error: fetch failed: AttributeError: listing exploded\n"
    assert handle.getReportSuites.call_count == 1


# --- one rsid column on a name that matches several suites ------------------

_MULTI_SUITES = [
    {"rsid": "rs-a", "name": "Shop"},
    {"rsid": "rs-b", "name": "shop"},
    {"rsid": "rs-c", "name": "Other"},
]

# (handler name, SDK method, component's own columns in order)
_OWN_RSID_COMMANDS = [
    (
        "run_list_segments",
        "getSegments",
        [
            "id",
            "name",
            "description",
            "rsid",
            "owner_id",
            "definition",
            "compatibility",
            "tags",
            "created",
            "modified",
            "extra",
        ],
    ),
    (
        "run_list_calculated_metrics",
        "getCalculatedMetrics",
        [
            "id",
            "name",
            "description",
            "rsid",
            "owner_id",
            "polarity",
            "precision",
            "type",
            "definition",
            "tags",
            "categories",
            "extra",
        ],
    ),
    ("run_list_classification_datasets", "getClassificationDatasets", ["id", "name", "rsid", "extra"]),
]


def _multi_suite_client(monkeypatch, sdk_method: str, own_rsid: str | None):
    """Real AaClient over a fake handle. Two suites (rs-a 'Shop', rs-b 'shop')
    match the identifier 'shop'. Each component row is tagged with the suite it
    was fetched for in its id; its own `rsid` field is `own_rsid`, or absent."""
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.resilience import RetryPolicy
    from aa_auto_sdr.cli.commands import inspect as cmd

    handle = MagicMock()
    handle.getReportSuites.side_effect = lambda rsid_list=None, **_: (
        [s for s in _MULTI_SUITES if s["rsid"] == rsid_list] if rsid_list else list(_MULTI_SUITES)
    )

    def rows(*_a, rsids_list=None, rsid=None, **_k):
        queried = rsids_list[0] if rsids_list else rsid
        row = {"id": f"c-{queried}", "name": f"N {queried}", "description": "d"}
        if own_rsid is not None:
            row["rsid"] = own_rsid
        return [row]

    getattr(handle, sdk_method).side_effect = rows
    client = AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy(max_retries=0))
    monkeypatch.setattr(cmd.credentials, "resolve", lambda **_: object())
    monkeypatch.setattr(cmd.AaClient, "from_credentials", lambda *_a, **_k: client)
    return cmd


_MULTI_KW = {"profile": None, "name_filter": None, "name_exclude": None, "sort_field": None, "limit": None}


@pytest.mark.parametrize(("handler", "sdk_method", "own_cols"), _OWN_RSID_COMMANDS)
def test_multimatch_csv_has_one_rsid_column(handler, sdk_method, own_cols, monkeypatch, capsys) -> None:
    import csv
    import io

    cmd = _multi_suite_client(monkeypatch, sdk_method, own_rsid=None)
    rc = getattr(cmd, handler)(identifier="shop", format_name="csv", output="-", **_MULTI_KW)
    assert rc == 0
    rows = list(csv.reader(io.StringIO(capsys.readouterr().out)))
    header, body = rows[0], rows[1:]
    assert header.count("rsid") == 1
    assert header == ["rsid", *[c for c in own_cols if c != "rsid"]]
    # The component's rsid defaults to the suite it was fetched for.
    by_id = {r[header.index("id")]: r[header.index("rsid")] for r in body}
    assert by_id == {"c-rs-a": "rs-a", "c-rs-b": "rs-b"}


@pytest.mark.parametrize(("handler", "sdk_method", "own_cols"), _OWN_RSID_COMMANDS)
def test_multimatch_table_has_one_rsid_column(handler, sdk_method, own_cols, monkeypatch, capsys) -> None:
    cmd = _multi_suite_client(monkeypatch, sdk_method, own_rsid=None)
    rc = getattr(cmd, handler)(identifier="shop", format_name=None, output=None, **_MULTI_KW)
    assert rc == 0
    header = capsys.readouterr().out.splitlines()[0].split()
    assert header.count("rsid") == 1


@pytest.mark.parametrize(("handler", "sdk_method", "own_cols"), _OWN_RSID_COMMANDS)
def test_multimatch_json_shape_is_unchanged(handler, sdk_method, own_cols, monkeypatch, capsys) -> None:
    """JSON already had one `rsid` key, first, holding the component's own
    value. Pin that exact shape: key order and the component's own rsid
    (a segment can carry an rsid other than the suite it was listed for)."""
    cmd = _multi_suite_client(monkeypatch, sdk_method, own_rsid="OWN")
    rc = getattr(cmd, handler)(identifier="shop", format_name="json", output="-", **_MULTI_KW)
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out, object_pairs_hook=list)
    assert [k for k, _ in parsed[0]] == ["rsid", *[c for c in own_cols if c != "rsid"]]
    assert [(dict(r)["id"], dict(r)["rsid"]) for r in parsed] == [("c-rs-a", "OWN"), ("c-rs-b", "OWN")]
