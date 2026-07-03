"""Tier-3 micro-optimizations: retention slice select, single-pass log
redaction. See .superpowers/sdd/task-8-brief.md for the full spec.

The colors._enabled cache micro (brief Step 5) was dropped per controller
review: it caches a process-global bool, and a global cache leaks the first
result across every later test in the process — poor risk/reward for a
microseconds-per-fragment saving (the brief's own risk assessment recommends
dropping it). `core/colors.py` is untouched.

The git skip-redundant-check micro (brief Step 6) has its test in
tests/snapshot/test_git_coverage.py, alongside the other git.py internals
tests it needs (monkeypatching `is_git_repository` / `_run_git`)."""

from __future__ import annotations

import logging
from pathlib import Path

from aa_auto_sdr.core.logging import SensitiveDataFilter
from aa_auto_sdr.snapshot.retention import RetentionPolicy, select_for_deletion


def test_keep_last_selects_all_but_last_k() -> None:
    files = [Path(f"2026-01-{d:02d}.json") for d in range(1, 6)]  # 5 files, sorted
    policy = RetentionPolicy(keep_last=2, keep_since=None)
    result = select_for_deletion(files, policy)  # returns a sorted list
    assert result == sorted(files[:-2])  # oldest 3 deleted, newest 2 kept


def test_sensitive_data_filter_second_pass_short_circuits() -> None:
    """A record carrying the `_redacted` marker from a first `filter()` pass
    is returned untouched by a second pass — this is the shape a single
    LogRecord actually takes in production, since a logger fans the same
    record out to multiple handlers (console + file), each with its own
    `SensitiveDataFilter` instance.

    Proof of the short-circuit: after the first pass sets `_redacted=True`,
    we mutate `record.msg` to text that WOULD be redacted if reprocessed;
    the second `filter()` call must leave it untouched."""
    f = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Bearer supersecrettoken123",
        args=None,
        exc_info=None,
    )

    assert f.filter(record) is True
    assert record._redacted is True
    assert "supersecrettoken123" not in record.msg

    record.msg = "Bearer shouldnotberedacted"  # would be redacted if reprocessed
    assert f.filter(record) is True
    assert record.msg == "Bearer shouldnotberedacted"  # unchanged: short-circuited
