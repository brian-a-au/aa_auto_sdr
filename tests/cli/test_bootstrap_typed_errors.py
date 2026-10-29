"""A failure building the client is a typed exit code, not a traceback.

`AaClient.from_credentials` retries `getCompanyId` and raises
`TransientApiError` (an `ApiError`) when the budget runs out, but every call
site caught only `AuthError`. A transient API failure during the auth
bootstrap therefore ended the run with a traceback and exit 1 instead of
api error 12.

`--watch` had no handling for any bootstrap failure, so missing credentials
and an auth failure also ended in a traceback.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.core.exceptions import ApiError, AuthError, ConfigError, TransientApiError
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

# Both shapes the bootstrap can raise: the retry-exhausted subclass the SDK
# boundary produces, and a plain ApiError.
_API_FAILURES = [
    pytest.param(TransientApiError("getCompanyId exhausted after 3 retries"), id="transient"),
    pytest.param(ApiError("502 Bad Gateway"), id="plain"),
]


@pytest.fixture
def authed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "id@AdobeOrg")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _commands():
    from aa_auto_sdr.cli.commands import discovery, inspect, inventory, stats

    return [
        pytest.param(
            "aa_auto_sdr.cli.commands.discovery.AaClient",
            lambda: discovery.run_list_reportsuites(**_LIST_KWARGS),
            id="list_reportsuites",
        ),
        pytest.param(
            "aa_auto_sdr.cli.commands.discovery.AaClient",
            lambda: discovery.run_list_virtual_reportsuites(**_LIST_KWARGS),
            id="list_virtual_reportsuites",
        ),
        pytest.param(
            "aa_auto_sdr.cli.commands.inspect.AaClient",
            lambda: inspect.run_list_metrics(identifier="demo.prod", **_LIST_KWARGS),
            id="list_metrics",
        ),
        pytest.param(
            "aa_auto_sdr.cli.commands.inspect.AaClient",
            lambda: inspect.run_describe_reportsuite(
                identifier="demo.prod",
                profile=None,
                format_name="json",
                output="-",
            ),
            id="describe_reportsuite",
        ),
        pytest.param(
            "aa_auto_sdr.cli.commands.stats.AaClient",
            lambda: stats.run(rsids=["demo.prod"], profile=None, format_name="json"),
            id="stats",
        ),
        pytest.param(
            "aa_auto_sdr.cli.commands.inventory.AaClient",
            lambda: inventory.run(rsids=["demo.prod"], profile=None, format_name="json"),
            id="inventory_summary",
        ),
    ]


@pytest.mark.parametrize(("target", "call"), _commands())
@pytest.mark.parametrize("exc", _API_FAILURES)
def test_bootstrap_api_failure_is_api_exit_code(target, call, exc, authed_env, capsys) -> None:
    with patch(target) as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = exc
        assert call() == ExitCode.API.value
    captured = capsys.readouterr()
    assert "api error:" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("exc", _API_FAILURES)
def test_generate_bootstrap_api_failure_is_api_exit_code(exc, authed_env, tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import generate

    with patch("aa_auto_sdr.cli.commands.generate.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = exc
        rc = generate.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == ExitCode.API.value
    assert "api error:" in capsys.readouterr().err


@pytest.mark.parametrize("exc", _API_FAILURES)
def test_generate_pipe_bootstrap_api_failure_emits_error_envelope(exc, authed_env, capsys) -> None:
    """On the stdout path the failure has to arrive as the JSON envelope on
    stderr, like every other pipe-path failure."""
    import json

    from aa_auto_sdr.cli.commands import generate

    with patch("aa_auto_sdr.cli.commands.generate.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = exc
        rc = generate.run(rsid="demo.prod", output_dir=Path("-"), format_name="json", profile=None)
    assert rc == ExitCode.API.value
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err.strip())["error"]["code"] == ExitCode.API.value


@pytest.mark.parametrize("exc", _API_FAILURES)
def test_batch_bootstrap_api_failure_is_api_exit_code(exc, authed_env, tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import batch

    with patch("aa_auto_sdr.cli.commands.batch.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = exc
        rc = batch.run(rsids=["demo.prod", "demo.staging"], output_dir=tmp_path, format_name="json", profile=None)
    assert rc == ExitCode.API.value
    assert "api error:" in capsys.readouterr().err


@pytest.mark.parametrize("exc", _API_FAILURES)
def test_interactive_bootstrap_api_failure_is_api_exit_code(exc, authed_env, capsys) -> None:
    from aa_auto_sdr.cli.commands import interactive

    with patch("aa_auto_sdr.cli.commands.interactive.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = exc
        assert interactive.run(profile=None) == ExitCode.API.value
    assert "api error:" in capsys.readouterr().err


@pytest.mark.parametrize("exc", _API_FAILURES)
def test_profile_test_bootstrap_api_failure_reports_fail(exc, authed_env, tmp_path: Path, capsys) -> None:
    """`--profile-test` reports PASS / FAIL on stdout as its result, so the
    api failure joins that report rather than going to stderr."""
    import json

    from aa_auto_sdr.cli.commands import profiles

    profile_dir = tmp_path / "orgs" / "prod"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(
        json.dumps({"org_id": "id@AdobeOrg", "client_id": "C", "secret": "S", "scopes": "X"}),
        encoding="utf-8",
    )
    with patch("aa_auto_sdr.api.client.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.side_effect = exc
        assert profiles.test_run("prod", base=tmp_path) == ExitCode.API.value
    assert "FAIL [api]" in capsys.readouterr().out


# --- watch ----------------------------------------------------------------


def _watch_ns(**overrides) -> argparse.Namespace:
    defaults = {
        "rsids": ["rs_a"],
        "watch": True,
        "interval": "1h",
        "watch_threshold": 1,
        "ignore_fields": None,
        "extended_fields": False,
        "format": None,
        "quality_policy": None,
        "fail_on_quality": None,
        "quality_report": None,
        "metrics_only": False,
        "dimensions_only": False,
        "profile": None,
        "snapshot_dir": None,
        "retry_policy": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.mark.parametrize(
    ("exc", "code", "label"),
    [
        (ConfigError("No credentials found."), ExitCode.CONFIG.value, "error:"),
        (AuthError("bad client_id"), ExitCode.AUTH.value, "auth error:"),
        (TransientApiError("getCompanyId exhausted"), ExitCode.API.value, "api error:"),
        (ApiError("502 Bad Gateway"), ExitCode.API.value, "api error:"),
    ],
    ids=["config", "auth", "transient_api", "plain_api"],
)
def test_watch_bootstrap_failures_are_typed_exit_codes(exc, code, label, authed_env, monkeypatch, capsys) -> None:
    """Watch had no handling for any bootstrap failure, so all four of these
    ended the run with a traceback and exit 1."""
    from aa_auto_sdr.cli.commands import watch

    if isinstance(exc, ConfigError):
        monkeypatch.setattr(
            "aa_auto_sdr.core.credentials.resolve",
            lambda **_kwargs: (_ for _ in ()).throw(exc),
        )
        assert watch.run(_watch_ns()) == code
    else:
        with patch("aa_auto_sdr.api.client.AaClient") as mock_client_cls:
            mock_client_cls.from_credentials.side_effect = exc
            assert watch.run(_watch_ns()) == code
    captured = capsys.readouterr()
    assert label in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    ("post_error", "code", "label"),
    [
        (None, ExitCode.AUTH.value, "auth error:"),
        (ApiError, ExitCode.API.value, "api error:"),
    ],
    ids=["rejected_credentials", "token_endpoint_unreachable"],
)
def test_sign_in_failure_reaches_the_cli_as_a_typed_code(post_error, code, label, authed_env, capsys) -> None:
    """End to end through the real SDK call path, with only the HTTP POST to
    the token endpoint stubbed. Rejected credentials used to surface as
    `TypeError: string indices must be integers` and exit 1."""
    import requests

    from aa_auto_sdr.cli.commands import discovery

    if post_error is None:
        # Adobe answers, but without a token: the SDK returns a JSON string.
        response = MagicMock()
        response.json.return_value = {"error": "invalid_client"}
        side_effect = lambda *_a, **_kw: response  # noqa: E731
    else:
        side_effect = requests.ConnectionError("connection refused")

    with patch("aanalytics2.connector.requests.post", side_effect=side_effect):
        assert discovery.run_list_reportsuites(**_LIST_KWARGS) == code
    captured = capsys.readouterr()
    assert label in captured.err
    assert captured.out == ""


def test_watch_bootstrap_success_still_starts_the_loop(authed_env, monkeypatch) -> None:
    """The positive control: a working bootstrap still reaches the loop."""
    from aa_auto_sdr.cli.commands import watch

    started: list[bool] = []
    monkeypatch.setattr(watch, "_build_real_fetcher", lambda _ns: MagicMock())
    monkeypatch.setattr(
        watch,
        "run_watch_loop",
        lambda **_kwargs: (started.append(True), (ExitCode.OK, 1))[1],
    )
    assert watch.run(_watch_ns()) == ExitCode.OK.value
    assert started == [True]
