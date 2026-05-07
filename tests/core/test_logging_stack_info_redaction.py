"""v1.5 carry-over #3 — exercise the record.stack_info redaction branch
in core/logging.SensitiveDataFilter.filter.

The v1.4 SensitiveDataFilter already redacts ``record.stack_info`` in place
(see core/logging.py); v1.4 lacked direct test coverage of that branch.
This test fills that gap so a future regression that drops or weakens the
stack_info path is caught immediately.
"""

from __future__ import annotations

import logging

from aa_auto_sdr.core.logging import SensitiveDataFilter


def test_stack_info_is_redacted():
    f = SensitiveDataFilter()
    record = logging.LogRecord(
        name="x",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="ordinary message",
        args=None,
        exc_info=None,
    )
    record.stack_info = "Stack (most recent call last):\n  Bearer abc.def.ghi\n"
    f.filter(record)
    assert "abc.def.ghi" not in record.stack_info
    assert "Bearer [REDACTED]" in record.stack_info


def test_stack_info_redacts_authorization_header():
    """A second pattern to lock in coverage breadth — ensures the stack_info
    branch goes through the full ``_redact_text`` regex chain, not just the
    Bearer pattern."""
    f = SensitiveDataFilter()
    record = logging.LogRecord(
        name="x",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="ordinary message",
        args=None,
        exc_info=None,
    )
    record.stack_info = "Stack (most recent call last):\n  Authorization: Bearer secret-token-value\n"
    f.filter(record)
    assert "secret-token-value" not in record.stack_info
    # Authorization: line is rewritten by its dedicated pattern.
    assert "Authorization: [REDACTED]" in record.stack_info


def test_stack_info_none_left_untouched():
    """When record.stack_info is None (the common case for non-debug-stack
    records), the filter should not raise and should leave the field None."""
    f = SensitiveDataFilter()
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ordinary message",
        args=None,
        exc_info=None,
    )
    assert record.stack_info is None
    f.filter(record)
    assert record.stack_info is None
