"""pipeline/models.py — RunResult.report_suite_name + BatchFailure + BatchResult."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult


def test_run_result_default_report_suite_name_is_none() -> None:
    r = RunResult(rsid="demo.prod", success=True, outputs=[Path("/tmp/demo.prod.json")])
    assert r.report_suite_name is None


def test_run_result_accepts_report_suite_name() -> None:
    r = RunResult(
        rsid="demo.prod",
        success=True,
        outputs=[Path("/tmp/demo.prod.json")],
        report_suite_name="Demo Production",
    )
    assert r.report_suite_name == "Demo Production"


def test_run_result_default_duration_seconds_is_zero() -> None:
    r = RunResult(rsid="demo.prod", success=True)
    assert r.duration_seconds == 0.0


def test_run_result_accepts_duration_seconds() -> None:
    r = RunResult(rsid="demo.prod", success=True, duration_seconds=2.5)
    assert r.duration_seconds == 2.5


def test_run_result_is_frozen() -> None:
    r = RunResult(rsid="demo.prod", success=True)
    with pytest.raises(FrozenInstanceError):
        r.rsid = "other"  # type: ignore[misc]


def test_batch_failure_construction() -> None:
    f = BatchFailure(
        rsid="bad.rsid",
        error_type="ApiError",
        message="rate limit exceeded",
        exit_code=12,
    )
    assert f.rsid == "bad.rsid"
    assert f.error_type == "ApiError"
    assert f.message == "rate limit exceeded"
    assert f.exit_code == 12


def test_batch_failure_is_frozen() -> None:
    f = BatchFailure(rsid="x", error_type="ApiError", message="m", exit_code=12)
    with pytest.raises(FrozenInstanceError):
        f.rsid = "y"  # type: ignore[misc]


def test_batch_result_construction() -> None:
    success = RunResult(rsid="ok.rs", success=True, outputs=[Path("/tmp/ok.rs.json")])
    failure = BatchFailure(rsid="bad.rs", error_type="ApiError", message="x", exit_code=12)
    br = BatchResult(
        successes=[success],
        failures=[failure],
        total_duration_seconds=4.2,
        total_output_bytes=1024,
    )
    assert br.successes == [success]
    assert br.failures == [failure]
    assert br.total_duration_seconds == 4.2
    assert br.total_output_bytes == 1024


def test_batch_result_is_frozen() -> None:
    br = BatchResult(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
    with pytest.raises(FrozenInstanceError):
        br.total_duration_seconds = 99.0  # type: ignore[misc]


def test_batch_result_empty_lists_are_independent_per_instance() -> None:
    """Frozen-with-default-list trap regression: each instance gets its own lists."""
    a = BatchResult(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
    b = BatchResult(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
    a.successes.append(RunResult(rsid="x", success=True))
    assert b.successes == []
