"""v1.4 — assert AaClient.from_credentials emits documented records.

Mocks aanalytics2 because we never want a real HTTP call from a unit test
(see CLAUDE.md: API 2.0 only, read-only — but unit tests should not call
out at all)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import AuthError


def _fake_credentials() -> Credentials:
    return Credentials(
        org_id="11112222@AdobeOrg",
        client_id="abcdef1234567890",
        secret="secret-shh",
        scopes="openid,AdobeID,additional_info.projectedProductContext",
        source="env",
    )


def _records_containing(caplog, substr: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if substr in r.getMessage()]


def test_from_credentials_logs_debug_after_configure(caplog):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.api.client")
    fake_login = MagicMock()
    fake_login.getCompanyId.return_value = [{"globalCompanyId": "co42"}]
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=fake_login),
        patch("aanalytics2.Analytics"),
    ):
        AaClient.from_credentials(_fake_credentials())
    debug_recs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    # Two DEBUG records: post-configure, post-getCompanyId.
    assert len(debug_recs) >= 2
    # The first DEBUG carries client_id_prefix (first 8 chars only).
    configure_rec = next(r for r in debug_recs if hasattr(r, "client_id_prefix"))
    assert configure_rec.client_id_prefix == "abcdef12"


def test_from_credentials_logs_info_on_bootstrap_success(caplog):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.api.client")
    fake_login = MagicMock()
    fake_login.getCompanyId.return_value = [{"globalCompanyId": "co42"}]
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=fake_login),
        patch("aanalytics2.Analytics"),
    ):
        client = AaClient.from_credentials(_fake_credentials())
    info_recs = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_recs) == 1
    rec = info_recs[0]
    assert rec.company_id == "co42"
    assert rec.company_id_source == "first_of_n"
    assert client.company_id == "co42"


def test_from_credentials_explicit_company_id_marks_source(caplog):
    caplog.set_level(logging.INFO, logger="aa_auto_sdr.api.client")
    fake_login = MagicMock()
    fake_login.getCompanyId.return_value = [
        {"globalCompanyId": "co1"},
        {"globalCompanyId": "co2"},
    ]
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=fake_login),
        patch("aanalytics2.Analytics"),
    ):
        AaClient.from_credentials(_fake_credentials(), company_id="co2")
    info_recs = [r for r in caplog.records if r.levelno == logging.INFO]
    rec = info_recs[0]
    assert rec.company_id == "co2"
    assert rec.company_id_source == "explicit"


def test_from_credentials_logs_auth_failure_on_no_companies(caplog):
    caplog.set_level(logging.ERROR, logger="aa_auto_sdr.api.client")
    fake_login = MagicMock()
    fake_login.getCompanyId.return_value = []
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=fake_login),
        pytest.raises(AuthError),
    ):
        AaClient.from_credentials(_fake_credentials())
    failures = _records_containing(caplog, "auth_failure")
    assert len(failures) == 1
    rec = failures[0]
    assert rec.levelno == logging.ERROR
    assert rec.reason == "no_companies"
    assert rec.error_class == "AuthError"


def test_from_credentials_logs_auth_failure_on_missing_global_company_id(caplog):
    caplog.set_level(logging.ERROR, logger="aa_auto_sdr.api.client")
    fake_login = MagicMock()
    fake_login.getCompanyId.return_value = [{"name": "co42"}]  # no globalCompanyId
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=fake_login),
        pytest.raises(AuthError),
    ):
        AaClient.from_credentials(_fake_credentials())
    failures = _records_containing(caplog, "auth_failure")
    assert len(failures) == 1
    assert failures[0].reason == "missing_global_company_id"
