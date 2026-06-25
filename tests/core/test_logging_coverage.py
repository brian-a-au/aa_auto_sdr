"""Coverage for defensive branches in core/logging.py.

Exercises the SensitiveDataFilter fallbacks (malformed %-format message,
formatException failure), JSONFormatter's underscore-skip and
unserializable-payload guards, and the _dep_summary missing-package path.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
import logging
import sys

import pytest

from aa_auto_sdr.core.logging import (
    JSONFormatter,
    SensitiveDataFilter,
    _dep_summary,
)


def _record(msg: object, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="x",
        lineno=1,
        msg=msg,
        args=args or None,
        exc_info=None,
    )


def test_filter_falls_back_to_raw_msg_on_format_mismatch() -> None:
    """A %-format string with mismatched args makes getMessage() raise; the
    filter must fall back to the raw msg rather than dropping the record."""
    f = SensitiveDataFilter()
    rec = _record("%d", "not-an-int")
    assert f.filter(rec) is True
    # Raw format string survives (redaction is a no-op on it).
    assert rec.msg == "%d"
    assert rec.args is None


def test_filter_uses_sentinel_when_formatexception_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """If pre-formatting the traceback raises, the redaction sentinel is stored
    in exc_text instead of leaking the raw exception."""

    def boom(self: logging.Formatter, ei: object) -> str:
        raise RuntimeError("formatException blew up")

    monkeypatch.setattr(logging.Formatter, "formatException", boom)

    try:
        raise ValueError("kaboom")
    except ValueError:
        rec = _record("oops")
        rec.exc_info = sys.exc_info()
        rec.exc_text = None

    f = SensitiveDataFilter()
    assert f.filter(rec) is True
    assert rec.exc_text == "[log-redaction-error]"
    assert rec.exc_info is None


def test_json_formatter_skips_underscore_prefixed_extra() -> None:
    """Record attributes whose name starts with '_' are not surfaced in JSON."""
    fmt = JSONFormatter(run_mode="single")
    rec = _record("hello")
    rec._private = "should-not-appear"  # type: ignore[attr-defined]
    payload = json.loads(fmt.format(rec))
    assert "_private" not in payload
    assert payload["message"] == "hello"


def test_json_formatter_uses_error_fallback_on_unserializable_payload() -> None:
    """A circular-reference extra makes json.dumps raise; the formatter must
    still emit a valid NDJSON object with the error-message sentinel."""
    fmt = JSONFormatter(run_mode="single")
    rec = _record("hello")
    circular: dict[str, object] = {}
    circular["self"] = circular
    rec.circular = circular  # type: ignore[attr-defined]
    payload = json.loads(fmt.format(rec))
    assert payload["message"] == "[json-format-error]"
    assert payload["run_mode"] == "single"
    assert payload["level"] == "INFO"


def test_dep_summary_reports_question_mark_for_missing_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a dependency is not installed, _dep_summary reports 'pkg=?' rather
    than raising."""

    def boom(name: str) -> str:
        raise importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib_metadata, "version", boom)
    result = _dep_summary()
    assert "aanalytics2=?" in result
    assert "pandas=?" in result
    assert "xlsxwriter=?" in result
