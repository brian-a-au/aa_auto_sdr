"""Lightweight timing instrumentation."""

from __future__ import annotations

from aa_auto_sdr.core import timings


def setup_function() -> None:
    timings.clear()
    # Default state must be disabled
    if timings._enabled:
        timings._enabled = False


def test_disabled_is_no_op() -> None:
    with timings.Timer("step"):
        pass
    assert timings.report() == []


def test_enabled_records() -> None:
    timings.enable()
    with timings.Timer("fetch"):
        pass
    with timings.Timer("build"):
        pass
    rep = timings.report()
    assert [label for label, _ in rep] == ["fetch", "build"]
    for _, secs in rep:
        assert secs >= 0


def test_clear_resets_records() -> None:
    timings.enable()
    with timings.Timer("a"):
        pass
    timings.clear()
    assert timings.report() == []


def test_timer_works_under_exception() -> None:
    timings.enable()
    try:
        with timings.Timer("x"):
            raise ValueError("oops")
    except ValueError:
        pass
    assert [label for label, _ in timings.report()] == ["x"]
