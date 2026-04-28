"""Client wrapper isolates the aanalytics2 SDK."""

from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api.client import AaClient
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
