"""The auth bootstrap normalizes SDK failures to the typed hierarchy.

`api/fetch.py::_retry_and_normalize` already wrapped any non-`ApiError` that
escaped a fetcher's retries, so the CLI's `except ApiError` saw one shape.
The bootstrap had no such step, so a network timeout or a bad SDK shape from
`getCompanyId` escaped raw and no caller caught it. Our own typed exceptions
pass through, and KeyboardInterrupt and SystemExit still propagate so a
Ctrl-C during the bootstrap is not reported as an API failure.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import ApiError, AuthError, ConfigError, TransientApiError

_NO_RETRIES = RetryPolicy(max_retries=0)


def _creds() -> Credentials:
    return Credentials(org_id="O", client_id="C", secret="S", scopes="X", source="env")


def _bootstrap(aa_module: MagicMock, error: BaseException) -> None:
    login = MagicMock()
    login.getCompanyId.side_effect = error
    aa_module.Login.return_value = login
    AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)


@patch("aa_auto_sdr.api.client.aanalytics2")
@pytest.mark.parametrize(
    "error",
    [
        requests.Timeout("read timed out"),
        requests.ConnectionError("connection refused"),
        AttributeError("bad SDK shape"),
        TypeError("unexpected payload"),
    ],
    ids=["timeout", "connection", "attribute", "type"],
)
def test_untyped_bootstrap_failure_becomes_api_error(aa_module: MagicMock, error) -> None:
    with pytest.raises(ApiError) as excinfo:
        _bootstrap(aa_module, error)
    assert type(error).__name__ in str(excinfo.value)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_transient_sdk_stub_stays_transient(aa_module: MagicMock) -> None:
    with pytest.raises(TransientApiError):
        _bootstrap(aa_module, KeyError("stub"))


@patch("aa_auto_sdr.api.client.aanalytics2")
@pytest.mark.parametrize(
    "error",
    [AuthError("bad client_id"), ConfigError("missing field")],
    ids=["auth", "config"],
)
def test_typed_errors_pass_through_unchanged(aa_module: MagicMock, error) -> None:
    """A typed error must keep its class so the caller's exit code is right."""
    with pytest.raises(type(error)):
        _bootstrap(aa_module, error)


@patch("aa_auto_sdr.api.client.aanalytics2")
@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(9)], ids=["sigint", "exit"])
def test_control_flow_still_propagates(aa_module: MagicMock, error) -> None:
    with pytest.raises(type(error)):
        _bootstrap(aa_module, error)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_successful_bootstrap_is_unchanged(aa_module: MagicMock) -> None:
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    client = AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)
    assert client.company_id == "abc123"
