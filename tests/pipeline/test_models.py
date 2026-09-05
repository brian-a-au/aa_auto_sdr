"""pipeline/models.py — RunResult.report_suite_name + BatchFailure + BatchResult."""

from dataclasses import FrozenInstanceError

import pytest

from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult


def test_run_result_is_frozen() -> None:
    r = RunResult(rsid="demo.prod", success=True)
    with pytest.raises(FrozenInstanceError):
        r.rsid = "other"  # type: ignore[misc]


def test_batch_failure_is_frozen() -> None:
    f = BatchFailure(rsid="x", error_type="ApiError", message="m", exit_code=12)
    with pytest.raises(FrozenInstanceError):
        f.rsid = "y"  # type: ignore[misc]


def test_batch_result_is_frozen() -> None:
    br = BatchResult(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
    with pytest.raises(FrozenInstanceError):
        br.total_duration_seconds = 99.0  # type: ignore[misc]


def test_batch_result_empty_lists_are_independent_per_instance() -> None:
    """Frozen-with-default-list trap regression: each instance gets its own lists."""
    a = BatchResult()
    b = BatchResult()
    a.successes.append(RunResult(rsid="x", success=True))
    a.failures.append(BatchFailure(rsid="y", error_type="ApiError", message="failed", exit_code=12))
    a.quality_verdicts["x"] = "pass"
    assert b.successes == []
    assert b.failures == []
    assert b.quality_verdicts == {}
