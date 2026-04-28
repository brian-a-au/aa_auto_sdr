"""SensitiveDataFilter: redact credentials in log records before format/emit.

Covers: Bearer tokens, Authorization headers, client_secret=, access_token=.
Must operate on both record.msg and record.args. Must never let a regex
exception leak the raw value."""

from __future__ import annotations

import logging

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
    ("msg", "expected_substr"),
    [
        ("Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig", "Bearer [REDACTED]"),
        ("Authorization: Bearer abc.def.ghi", "Authorization: [REDACTED]"),
        ("client_secret=p1-abcdef0123_456", "client_secret=[REDACTED]"),
        ("access_token=mytoken123", "access_token=[REDACTED]"),
    ],
)
def test_redacts_pattern(msg: str, expected_substr: str) -> None:
    f = SensitiveDataFilter()
    rec = _record(msg)
    assert f.filter(rec) is True  # filter returns True meaning "let record through"
    assert expected_substr in rec.getMessage()
    assert "eyJhbGciOiJSUzI1NiJ9" not in rec.getMessage()
    assert "abc.def.ghi" not in rec.getMessage()


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
    rec.normal_field = "ok"  # type: ignore[attr-defined]
    f.filter(rec)
    assert rec.client_secret == "[REDACTED]"  # type: ignore[attr-defined]
    assert rec.access_token == "[REDACTED]"  # type: ignore[attr-defined]
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
