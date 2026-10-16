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


def test_format_report_empty_returns_no_records_marker() -> None:
    """The empty path should print a clear `(no timings recorded)` marker."""
    timings.disable()
    timings.clear()
    out = timings.format_report()
    assert "Timings:" in out
    assert "(no timings recorded)" in out


def test_format_report_with_overlapping_records_renders_summed_stage_time() -> None:
    """Overlapping worker stages sum without claiming command elapsed time."""
    out = timings.format_report([("build:worker-1", 0.250), ("build:worker-2", 0.500)])
    assert "build:worker-1" in out
    assert "build:worker-2" in out
    assert "Summed stage time" in out
    assert "Total" not in out
    assert "elapsed" not in out
    # total should be 0.750, formatted as "0.750s"
    assert "0.750s" in out
