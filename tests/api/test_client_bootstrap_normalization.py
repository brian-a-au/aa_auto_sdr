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


# --- the steps around getCompanyId ----------------------------------------
#
# `Login()` is where the SDK exchanges the credentials for an OAuth token, so
# it is the step most likely to fail in the field. `configure` and
# `Analytics()` bracket the retried call. All three sat outside the
# normalizer, so a failure in any of them escaped raw.


@patch("aa_auto_sdr.api.client.aanalytics2")
@pytest.mark.parametrize("step", ["configure", "Login", "Analytics"], ids=["configure", "login", "analytics"])
def test_untyped_failure_in_any_bootstrap_step_becomes_api_error(aa_module: MagicMock, step) -> None:
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    getattr(aa_module, step).side_effect = requests.ConnectionError("connection refused")
    with pytest.raises(ApiError) as excinfo:
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)
    assert "ConnectionError" in str(excinfo.value)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_rejected_credentials_are_an_auth_error(aa_module: MagicMock) -> None:
    """The SDK's token helper returns a JSON *string* when the token endpoint
    rejects the credentials, so `AdobeRequest.__init__` then indexes a str and
    raises TypeError out of `Login()`. That is a sign-in failure, and the
    message has to point at the credentials rather than read as a crash."""
    aa_module.Login.side_effect = TypeError("string indices must be integers, not 'str'")
    with pytest.raises(AuthError) as excinfo:
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)
    message = str(excinfo.value).lower()
    assert "client_id" in message
    assert "secret" in message


@patch("aa_auto_sdr.api.client.aanalytics2")
@pytest.mark.parametrize("step", ["configure", "Login", "Analytics"], ids=["configure", "login", "analytics"])
def test_control_flow_in_any_bootstrap_step_still_propagates(aa_module: MagicMock, step) -> None:
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    getattr(aa_module, step).side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_both_token_exchanges_report_the_same_way(aa_module: MagicMock) -> None:
    """`Analytics()` performs a second token exchange: `configure` leaves an
    empty token in the SDK's global config and `AdobeRequest` deepcopies
    rather than mutating it, so the handle's own request re-runs the POST. If
    that one answers without a token, the same string-indexing TypeError
    arises, and it has to read as a sign-in failure rather than as
    "api error: ... TypeError: string indices must be integers"."""
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    aa_module.Analytics.side_effect = TypeError("string indices must be integers, not 'str'")
    with pytest.raises(AuthError) as excinfo:
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)
    assert "string indices" not in str(excinfo.value)
    assert "access token" in str(excinfo.value).lower()


@patch("aa_auto_sdr.api.client.aanalytics2")
@pytest.mark.parametrize(
    "companies",
    [["globalcompany"], [None], [7], "globalcompany", {"globalCompanyId": "abc"}],
    ids=["list_of_str", "list_of_none", "list_of_int", "bare_str", "bare_dict"],
)
def test_unexpected_company_shape_becomes_api_error(aa_module: MagicMock, companies) -> None:
    """`getCompanyId` returns `json_res['imsOrgs'][0]['companies']` verbatim
    under a bare `except`, so whatever Adobe puts there reaches us. Reading
    that shape sat outside the normalizer, so an `AttributeError` escaped
    every handler and the run ended with a traceback and exit 1."""
    aa_module.Login.return_value.getCompanyId.return_value = companies
    with pytest.raises(ApiError):
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_no_companies_is_still_an_auth_error(aa_module: MagicMock) -> None:
    """The typed AuthError raised while reading the shape has to survive the
    normalizer that now wraps that block."""
    aa_module.Login.return_value.getCompanyId.return_value = []
    with pytest.raises(AuthError, match="Product Profile"):
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_missing_global_company_id_is_still_an_auth_error(aa_module: MagicMock) -> None:
    aa_module.Login.return_value.getCompanyId.return_value = [{"companyName": "Acme"}]
    with pytest.raises(AuthError, match="globalCompanyId"):
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_an_unrelated_type_error_is_not_blamed_on_the_credentials(aa_module: MagicMock) -> None:
    """Only the SDK's string-indexing shape means "no access token". An
    unrelated TypeError, such as a signature change after an SDK upgrade,
    must not tell the user to rotate working credentials."""
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    aa_module.Analytics.side_effect = TypeError("__init__() got an unexpected keyword argument 'company'")
    with pytest.raises(ApiError) as excinfo:
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)
    assert "unexpected keyword argument" in str(excinfo.value)
    assert "client_id" not in str(excinfo.value)


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_typed_error_from_a_bootstrap_step_passes_through(aa_module: MagicMock) -> None:
    aa_module.Login.side_effect = AuthError("integration not in a product profile")
    with pytest.raises(AuthError, match="product profile"):
        AaClient.from_credentials(_creds(), retry_policy=_NO_RETRIES)
