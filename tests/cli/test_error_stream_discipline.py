"""Error messages belong on stderr, so stdout stays a machine-readable stream.

Generate, batch, diff, and render-from already print their errors to stderr.
The discovery, inspection, stats, inventory, trending, snapshot-lifecycle,
profile, and config handlers printed them to stdout, so a run that failed
put a human sentence in the stream a caller was parsing. `--agent-mode`
expands to `--format json --output -`, which made that the default shape for
an agent reading these commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import discovery as discovery_cmd
from aa_auto_sdr.cli.commands import inspect as inspect_cmd
from aa_auto_sdr.cli.commands import inventory as inventory_cmd
from aa_auto_sdr.cli.commands import profiles as profiles_cmd
from aa_auto_sdr.cli.commands import snapshots as snapshots_cmd
from aa_auto_sdr.cli.commands import stats as stats_cmd
from aa_auto_sdr.cli.commands import trending as trending_cmd
from aa_auto_sdr.core.exceptions import ApiError, AuthError
from aa_auto_sdr.core.exit_codes import ExitCode

_LIST_KWARGS = {
    "profile": None,
    "format_name": "json",
    "output": "-",
    "name_filter": None,
    "name_exclude": None,
    "sort_field": None,
    "limit": None,
}


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An empty working directory with no credential env vars."""
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def authed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _config_error_cases():
    return [
        pytest.param(lambda: discovery_cmd.run_list_reportsuites(**_LIST_KWARGS), id="list_reportsuites"),
        pytest.param(
            lambda: discovery_cmd.run_list_virtual_reportsuites(**_LIST_KWARGS),
            id="list_virtual_reportsuites",
        ),
        pytest.param(
            lambda: inspect_cmd.run_list_metrics(identifier="demo.prod", **_LIST_KWARGS),
            id="list_metrics",
        ),
        pytest.param(
            lambda: inspect_cmd.run_list_dimensions(identifier="demo.prod", **_LIST_KWARGS),
            id="list_dimensions",
        ),
        pytest.param(
            lambda: inspect_cmd.run_describe_reportsuite(
                identifier="demo.prod",
                profile=None,
                format_name="json",
                output="-",
            ),
            id="describe_reportsuite",
        ),
        pytest.param(lambda: stats_cmd.run(rsids=["demo.prod"], profile=None, format_name="json"), id="stats"),
        pytest.param(
            lambda: inventory_cmd.run(rsids=["demo.prod"], profile=None, format_name="json"),
            id="inventory_summary",
        ),
        pytest.param(lambda: config_cmd.validate_config(profile=None), id="validate_config"),
        pytest.param(lambda: config_cmd.show_config(profile=None), id="show_config"),
    ]


@pytest.mark.parametrize("call", _config_error_cases())
def test_missing_credentials_reports_on_stderr(call, no_credentials, capsys) -> None:
    assert call() == ExitCode.CONFIG.value
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


def test_discovery_auth_failure_reports_on_stderr(authed_env, capsys) -> None:
    with patch("aa_auto_sdr.cli.commands.discovery.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = AuthError("bad client_id")
        assert discovery_cmd.run_list_reportsuites(**_LIST_KWARGS) == ExitCode.AUTH.value
    captured = capsys.readouterr()
    assert "auth error:" in captured.err
    assert captured.out == ""


def test_discovery_api_failure_reports_on_stderr(authed_env, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        discovery_cmd.fetch,
        "fetch_report_suite_summaries",
        lambda _client: (_ for _ in ()).throw(ApiError("rate limited")),
    )
    with patch("aa_auto_sdr.cli.commands.discovery.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")
        assert discovery_cmd.run_list_reportsuites(**_LIST_KWARGS) == ExitCode.API.value
    captured = capsys.readouterr()
    assert "api error:" in captured.err
    assert captured.out == ""


def test_inspect_api_failure_reports_on_stderr(authed_env, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        inspect_cmd.fetch,
        "resolve_rsid",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ApiError("rate limited")),
    )
    with patch("aa_auto_sdr.cli.commands.inspect.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")
        assert inspect_cmd.run_list_metrics(identifier="demo.prod", **_LIST_KWARGS) == ExitCode.API.value
    captured = capsys.readouterr()
    assert "api error:" in captured.err
    assert captured.out == ""


def test_snapshot_lifecycle_usage_errors_report_on_stderr(capsys) -> None:
    assert snapshots_cmd.list_run(profile=None, rsid=None, format_name="json", snapshot_dir=None) == (
        ExitCode.CONFIG.value
    )
    first = capsys.readouterr()
    assert "error:" in first.err
    assert first.out == ""

    assert (
        snapshots_cmd.prune_run(
            profile=None,
            rsid=None,
            keep_last=None,
            keep_since=None,
            dry_run=True,
            assume_yes=True,
            snapshot_dir=None,
        )
        == ExitCode.CONFIG.value
    )
    second = capsys.readouterr()
    assert "error:" in second.err
    assert second.out == ""


def test_snapshot_list_bad_format_reports_on_stderr(tmp_path: Path, capsys) -> None:
    rc = snapshots_cmd.list_run(profile=None, rsid=None, format_name="yaml", snapshot_dir=tmp_path)
    assert rc == ExitCode.OUTPUT.value
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "yaml" in captured.err


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"rsids": [], "duration": "30d"}, ExitCode.USAGE.value),
        ({"rsids": ["demo.prod"], "duration": "forever"}, ExitCode.USAGE.value),
    ],
    ids=["no_rsids", "bad_duration"],
)
def test_trending_argument_errors_report_on_stderr(kwargs, code, tmp_path: Path, capsys) -> None:
    rc = trending_cmd.run(
        snapshot_dir=tmp_path,
        profile=None,
        format_name="json",
        output="-",
        **kwargs,
    )
    assert rc == code
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


def test_trending_bad_format_reports_on_stderr(tmp_path: Path, capsys) -> None:
    rc = trending_cmd.run(
        rsids=["demo.prod"],
        duration="30d",
        snapshot_dir=tmp_path,
        profile=None,
        format_name="yaml",
        output="-",
    )
    assert rc == ExitCode.OUTPUT.value
    assert "error:" in capsys.readouterr().err


def test_trending_without_snapshot_dir_reports_on_stderr(capsys) -> None:
    rc = trending_cmd.run(
        rsids=["demo.prod"],
        duration="30d",
        snapshot_dir=None,
        profile=None,
        format_name="json",
        output="-",
    )
    assert rc == ExitCode.CONFIG.value
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


def test_profile_import_errors_report_on_stderr(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "nope.json"
    assert profiles_cmd.import_run("p", str(missing), base=tmp_path) == ExitCode.CONFIG.value
    first = capsys.readouterr()
    assert "error:" in first.err
    assert first.out == ""

    not_an_object = tmp_path / "list.json"
    not_an_object.write_text("[]", encoding="utf-8")
    assert profiles_cmd.import_run("p", str(not_an_object), base=tmp_path) == ExitCode.CONFIG.value
    second = capsys.readouterr()
    assert "error:" in second.err
    assert second.out == ""

    incomplete = tmp_path / "partial.json"
    incomplete.write_text(json.dumps({"org_id": "O"}), encoding="utf-8")
    assert profiles_cmd.import_run("p", str(incomplete), base=tmp_path) == ExitCode.CONFIG.value
    third = capsys.readouterr()
    assert "error:" in third.err
    assert third.out == ""


def test_profile_show_missing_reports_on_stderr(tmp_path: Path, capsys) -> None:
    assert profiles_cmd.show_run("absent", base=tmp_path) == ExitCode.CONFIG.value
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


def test_successful_listing_still_writes_json_to_stdout(authed_env, monkeypatch, capsys) -> None:
    """The positive control: fixing the error stream must not move the payload."""
    from aa_auto_sdr.api import models

    monkeypatch.setattr(
        discovery_cmd.fetch,
        "fetch_report_suite_summaries",
        lambda _client: [models.ReportSuiteSummary(rsid="demo.prod", name="Demo")],
    )
    with patch("aa_auto_sdr.cli.commands.discovery.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")
        assert discovery_cmd.run_list_reportsuites(**_LIST_KWARGS) == ExitCode.OK.value
    captured = capsys.readouterr()
    assert json.loads(captured.out)[0]["rsid"] == "demo.prod"
    assert "error:" not in captured.err
