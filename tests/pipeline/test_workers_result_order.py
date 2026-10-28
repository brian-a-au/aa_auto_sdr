"""A parallel batch reports results in input order.

`run_parallel` appended to `successes` and `failures` as futures completed,
so the summary banner rows and the `rsids` array in `--run-summary-json`
came out in a different order on every run once `--workers` was 2 or more.
The sequential path keeps input order, and a CI diff of the summary should
not change just because one report suite answered faster.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import ApiError, ReportSuiteNotFoundError
from aa_auto_sdr.pipeline import workers
from aa_auto_sdr.pipeline.models import RunResult

# Reverse of the input order, so completion order cannot match by luck.
_DELAYS = {"rs_a": 0.30, "rs_b": 0.20, "rs_c": 0.10}
_RSIDS = ["rs_a", "rs_b", "rs_c"]


def _run(rsids: list[str], *, fail_fast: bool = False, workers_count: int = 3):
    return workers.run_parallel(
        client=None,
        rsids=rsids,
        formats=["json"],
        output_dir=Path("."),
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="1.24.4",
        workers=workers_count,
        fail_fast=fail_fast,
    )


@pytest.fixture
def slowest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(*, rsid: str, **_kwargs) -> RunResult:
        time.sleep(_DELAYS[rsid])
        return RunResult(rsid=rsid, success=True, outputs=[], report_suite_name=rsid)

    monkeypatch.setattr(workers, "_run_single_for_batch", fake)


def test_successes_follow_input_order(slowest_first) -> None:
    result = _run(_RSIDS)
    assert [ok.rsid for ok in result.successes] == _RSIDS


def test_successes_follow_input_order_with_one_worker_pool(slowest_first) -> None:
    result = _run(_RSIDS, workers_count=2)
    assert [ok.rsid for ok in result.successes] == _RSIDS


def test_failures_follow_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(*, rsid: str, **_kwargs) -> RunResult:
        time.sleep(_DELAYS[rsid])
        raise ApiError(f"{rsid} unavailable")

    monkeypatch.setattr(workers, "_run_single_for_batch", fake)
    result = _run(_RSIDS)
    assert [bad.rsid for bad in result.failures] == _RSIDS


def test_mixed_outcomes_each_follow_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(*, rsid: str, **_kwargs) -> RunResult:
        time.sleep(_DELAYS[rsid])
        if rsid in ("rs_a", "rs_c"):
            raise ApiError(f"{rsid} unavailable")
        return RunResult(rsid=rsid, success=True, outputs=[], report_suite_name=rsid)

    monkeypatch.setattr(workers, "_run_single_for_batch", fake)
    result = _run(_RSIDS)
    assert [ok.rsid for ok in result.successes] == ["rs_b"]
    assert [bad.rsid for bad in result.failures] == ["rs_a", "rs_c"]


def test_fail_fast_exit_code_comes_from_the_last_real_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """With input order restored, the chosen code no longer depends on which
    worker happened to finish first."""

    def fake(*, rsid: str, **_kwargs) -> RunResult:
        time.sleep(_DELAYS[rsid])
        if rsid == "rs_a":
            raise ReportSuiteNotFoundError("rs_a missing")
        raise ApiError(f"{rsid} unavailable")

    monkeypatch.setattr(workers, "_run_single_for_batch", fake)
    result = _run(_RSIDS, fail_fast=True)
    real = [bad for bad in result.failures if bad.error_type != "CancelledError"]
    assert [bad.rsid for bad in real] == sorted(bad.rsid for bad in real)
    assert [bad.rsid for bad in result.failures] == _RSIDS


def test_every_rsid_is_accounted_for_once(slowest_first) -> None:
    result = _run(_RSIDS)
    reported = [ok.rsid for ok in result.successes] + [bad.rsid for bad in result.failures]
    assert sorted(reported) == sorted(_RSIDS)
