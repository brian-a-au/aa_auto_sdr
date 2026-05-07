"""v1.5 — credentials.resolve emits DEBUG per source attempted, INFO with
creds_source on the matching source, ERROR on ConfigError."""

from __future__ import annotations

import logging

import pytest

from aa_auto_sdr.core.credentials import resolve
from aa_auto_sdr.core.exceptions import ConfigError


@pytest.fixture(autouse=True)
def _isolate_package_logger():
    """Pattern B per disambiguation table — resolve() doesn't call setup_logging."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    pkg.handlers.clear()
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)


def test_resolve_via_env_emits_creds_source(caplog, monkeypatch, tmp_path):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.core.credentials")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ORG_ID", "id@AdobeOrg")
    monkeypatch.setenv("CLIENT_ID", "ci")
    monkeypatch.setenv("SECRET", "s")
    monkeypatch.setenv("SCOPES", "openid,AdobeID,additional_info.projectedProductContext")
    monkeypatch.delenv("AA_PROFILE", raising=False)

    resolve()

    info_recs = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_recs) == 1
    assert info_recs[0].creds_source == "env"


def test_resolve_no_credentials_emits_error(caplog, monkeypatch, tmp_path):
    caplog.set_level(logging.ERROR, logger="aa_auto_sdr.core.credentials")
    monkeypatch.chdir(tmp_path)
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(ConfigError):
        resolve()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].error_class == "ConfigError"
