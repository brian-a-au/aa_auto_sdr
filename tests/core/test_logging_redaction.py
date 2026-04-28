"""SensitiveDataFilter: redact credentials in log records before format/emit.

Covers: Bearer tokens, Authorization headers, client_secret=, access_token=.
Must operate on both record.msg and record.args. Must never let a regex
exception leak the raw value."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from aa_auto_sdr.core.logging import SensitiveDataFilter


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="x",
        lineno=1,
        msg=msg,
        args=args or None,
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("msg", "raw_secret_must_not_appear"),
    [
        ("Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig", "eyJhbGciOiJSUzI1NiJ9.payload.sig"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("client_secret=p1-abcdef0123_456", "p1-abcdef0123_456"),
        ("access_token=mytoken123", "mytoken123"),
        # v1.3.0 review fix — non-Bearer Authorization schemes
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("Authorization: Digest username=admin response=xyz789", "xyz789"),
        # v1.3.0 review fix — case-insensitive matching
        ("authorization: bearer abc.def.ghi", "abc.def.ghi"),
        ("BEARER eyJtest.abc.123", "eyJtest.abc.123"),
        ("CLIENT_SECRET=p1-secretvalue", "p1-secretvalue"),
        ("ACCESS_TOKEN=token-xyz-123", "token-xyz-123"),
        # v1.3.0 pre-merge review — Adobe IMS token-response shapes (id_token / refresh_token / jwt_token)
        ("id_token=eyJpdGVzdC5hYmMuZGVm", "eyJpdGVzdC5hYmMuZGVm"),
        ("ID_TOKEN=eyJpZHRva2VuLmFiYy5kZWY", "eyJpZHRva2VuLmFiYy5kZWY"),
        ("refresh_token=p1-refresh-secret-value", "p1-refresh-secret-value"),
        ("REFRESH_TOKEN=rt-XYZ-123", "rt-XYZ-123"),
        ("jwt_token=eyJqd3QtdG9rZW4tdmFs", "eyJqd3QtdG9rZW4tdmFs"),
        ("jwt-token=eyJkYXNoLXZhcmlhbnQ", "eyJkYXNoLXZhcmlhbnQ"),
        # POST body shape — `aanalytics2` SDK at DEBUG dumps form-encoded responses
        (
            "POST /ims/token: id_token=eyJtest.abc.def&access_token=mytoken123&refresh_token=rt456",
            "eyJtest.abc.def",
        ),
    ],
)
def test_redacts_pattern(msg: str, raw_secret_must_not_appear: str) -> None:
    f = SensitiveDataFilter()
    rec = _record(msg)
    assert f.filter(rec) is True  # filter returns True meaning "let record through"
    formatted = rec.getMessage()
    assert "[REDACTED]" in formatted
    assert raw_secret_must_not_appear not in formatted


def test_redacts_in_args() -> None:
    f = SensitiveDataFilter()
    rec = _record("token: %s", "Bearer eyJtest.abc.123")
    f.filter(rec)
    formatted = rec.getMessage()
    assert "Bearer [REDACTED]" in formatted
    assert "eyJtest.abc.123" not in formatted


def test_passthrough_when_no_secret() -> None:
    f = SensitiveDataFilter()
    rec = _record("Hello world")
    f.filter(rec)
    assert rec.getMessage() == "Hello world"


def test_redacts_extra_dict_keys() -> None:
    f = SensitiveDataFilter()
    rec = _record("login result")
    rec.client_secret = "p1-secret-value"  # type: ignore[attr-defined]
    rec.access_token = "raw-bearer"  # type: ignore[attr-defined]
    rec.id_token = "raw-id-token"  # type: ignore[attr-defined]
    rec.refresh_token = "raw-refresh-token"  # type: ignore[attr-defined]
    rec.jwt_token = "raw-jwt-token"  # type: ignore[attr-defined]
    rec.normal_field = "ok"  # type: ignore[attr-defined]
    f.filter(rec)
    assert rec.client_secret == "[REDACTED]"  # type: ignore[attr-defined]
    assert rec.access_token == "[REDACTED]"  # type: ignore[attr-defined]
    assert rec.id_token == "[REDACTED]"  # type: ignore[attr-defined]
    assert rec.refresh_token == "[REDACTED]"  # type: ignore[attr-defined]
    assert rec.jwt_token == "[REDACTED]"  # type: ignore[attr-defined]
    assert rec.normal_field == "ok"  # type: ignore[attr-defined]


def test_regex_failure_does_not_leak_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the redaction regex raises (extreme edge case), the value MUST NOT
    appear in the formatted output. We replace it with the error sentinel."""
    import aa_auto_sdr.core.logging as logmod

    def boom(_pattern, _replacement, _text):
        raise ValueError("regex blew up")

    monkeypatch.setattr(logmod.re, "sub", boom)
    f = SensitiveDataFilter()
    rec = _record("Bearer secret-token-abcxyz")
    f.filter(rec)
    msg = rec.getMessage()
    assert "secret-token-abcxyz" not in msg
    assert "[log-redaction-error]" in msg


def test_setup_logging_wires_redaction_to_file_handler(tmp_path: Path) -> None:
    """Integration test: redaction must apply through setup_logging-wired handlers,
    not just when SensitiveDataFilter is invoked directly. Catches future regressions
    where a refactor drops the addFilter calls in setup_logging."""
    import argparse

    from aa_auto_sdr.core.logging import setup_logging

    ns = argparse.Namespace(
        log_level="INFO",
        log_format="text",
        quiet=False,
        rsids=["abc"],
        batch=[],
        diff=None,
        list_reportsuites=False,
        list_virtual_reportsuites=False,
        describe_reportsuite=None,
        list_metrics=None,
        list_dimensions=None,
        list_segments=None,
        list_calculated_metrics=None,
        list_classification_datasets=None,
        list_snapshots=False,
        prune_snapshots=False,
        profile_add=None,
        profile_test=None,
        profile_show=None,
        profile_list=False,
        profile_import=None,
        show_config=False,
        config_status=False,
        validate_config=False,
        sample_config=False,
        stats=False,
        interactive=False,
    )
    setup_logging(ns, log_dir=tmp_path / "logs")
    try:
        logging.getLogger("aa_auto_sdr.test").info("Bearer eyJsetup.abc.xyz123")
        for h in logging.root.handlers:
            h.flush()
        log_file = next((tmp_path / "logs").glob("SDR_Generation_abc_*.log"))
        text = log_file.read_text(encoding="utf-8")
        assert "[REDACTED]" in text
        assert "eyJsetup.abc.xyz123" not in text
    finally:
        # Teardown: clean up handlers since we don't have the autouse fixture here
        for h in logging.root.handlers[:]:
            h.close()
            logging.root.removeHandler(h)
