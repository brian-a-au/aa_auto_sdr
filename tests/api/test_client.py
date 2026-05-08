"""Client wrapper isolates the aanalytics2 SDK."""

from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import DEFAULT_RETRY_POLICY, RetryPolicy
from aa_auto_sdr.core.credentials import Credentials


def _creds() -> Credentials:
    return Credentials(
        org_id="O",
        client_id="C",
        secret="S",
        scopes="X",
        source="env",
    )


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_resolves_company_id_then_constructs_analytics(aa_module: MagicMock) -> None:
    """Real flow: configure → Login().getCompanyId() → Analytics(globalCompanyId)."""
    login_obj = MagicMock()
    login_obj.getCompanyId.return_value = [
        {"globalCompanyId": "abc123", "companyName": "Acme"},
    ]
    aa_module.Login.return_value = login_obj
    aa_module.Analytics.return_value = MagicMock()

    AaClient.from_credentials(_creds())

    aa_module.configure.assert_called_once()
    aa_module.Login.assert_called_once()
    login_obj.getCompanyId.assert_called_once()
    aa_module.Analytics.assert_called_once_with("abc123")


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_exposes_underlying_handle(aa_module: MagicMock) -> None:
    handle = MagicMock()
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    aa_module.Analytics.return_value = handle
    client = AaClient.from_credentials(_creds())
    assert client.handle is handle


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_records_company_id(aa_module: MagicMock) -> None:
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    aa_module.Analytics.return_value = MagicMock()
    client = AaClient.from_credentials(_creds())
    assert client.company_id == "abc123"


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_uses_explicit_company_id_when_provided(aa_module: MagicMock) -> None:
    """If creds carry SPIKE_COMPANY_ID-style override, use it instead of [0]."""
    aa_module.Login.return_value.getCompanyId.return_value = [
        {"globalCompanyId": "first"},
        {"globalCompanyId": "second"},
    ]
    aa_module.Analytics.return_value = MagicMock()
    client = AaClient.from_credentials(_creds(), company_id="second")
    assert client.company_id == "second"
    aa_module.Analytics.assert_called_once_with("second")


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_raises_when_no_companies_visible(aa_module: MagicMock) -> None:
    from aa_auto_sdr.core.exceptions import AuthError

    aa_module.Login.return_value.getCompanyId.return_value = []
    with pytest.raises(AuthError):
        AaClient.from_credentials(_creds())


def _build_creds() -> Credentials:
    """Minimal Credentials instance whose .validate() passes."""
    return Credentials(
        org_id="org@AdobeOrg",
        client_id="abcdef0123",
        secret="s3cret",
        scopes="openid,AdobeID,additional_info.projectedProductContext",
        source="env",
    )


class TestRetryPolicyThreading:
    def test_default_policy_when_unset(self) -> None:
        creds = _build_creds()
        with (
            patch("aa_auto_sdr.api.client.aanalytics2.configure"),
            patch("aa_auto_sdr.api.client.aanalytics2.Login") as login_cls,
            patch("aa_auto_sdr.api.client.aanalytics2.Analytics") as analytics_cls,
        ):
            login_cls.return_value.getCompanyId.return_value = [{"globalCompanyId": "co"}]
            analytics_cls.return_value = MagicMock()
            client = AaClient.from_credentials(creds)
        assert client.retry_policy == DEFAULT_RETRY_POLICY

    def test_custom_policy_propagates(self) -> None:
        creds = _build_creds()
        policy = RetryPolicy(max_retries=6, base_delay=1.0, max_delay=30.0)
        with (
            patch("aa_auto_sdr.api.client.aanalytics2.configure"),
            patch("aa_auto_sdr.api.client.aanalytics2.Login") as login_cls,
            patch("aa_auto_sdr.api.client.aanalytics2.Analytics") as analytics_cls,
        ):
            login_cls.return_value.getCompanyId.return_value = [{"globalCompanyId": "co"}]
            analytics_cls.return_value = MagicMock()
            client = AaClient.from_credentials(creds, retry_policy=policy)
        assert client.retry_policy == policy

    def test_get_company_id_is_retried_on_transient_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """getCompanyId bootstrap retries on TransientApiError."""
        from aa_auto_sdr.core.exceptions import TransientApiError

        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
        creds = _build_creds()
        # Login.getCompanyId fails twice with TransientApiError, then succeeds.
        get_company_id = MagicMock(
            side_effect=[
                TransientApiError("transient bootstrap fail"),
                TransientApiError("transient bootstrap fail"),
                [{"globalCompanyId": "co"}],
            ]
        )
        with (
            patch("aa_auto_sdr.api.client.aanalytics2.configure"),
            patch("aa_auto_sdr.api.client.aanalytics2.Login") as login_cls,
            patch("aa_auto_sdr.api.client.aanalytics2.Analytics") as analytics_cls,
        ):
            login_cls.return_value.getCompanyId = get_company_id
            analytics_cls.return_value = MagicMock()
            client = AaClient.from_credentials(creds)
        assert client.company_id == "co"
        assert get_company_id.call_count == 3
