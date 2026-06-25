"""Worker pool — coverage for callback, cancel, and interrupt branches."""

from __future__ import annotations

from concurrent.futures import CancelledError
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.core.exceptions import AaAutoSdrError, ApiError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.pipeline.models import RunResult
from aa_auto_sdr.pipeline.workers import _exit_code_for, run_parallel


def _success_result(rsid: str) -> RunResult:
    return RunResult(
        rsid=rsid,
        success=True,
        outputs=[Path(f"/tmp/{rsid}.json")],
        duration_seconds=0.01,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def base_kwargs(tmp_path: Path, mock_client: MagicMock) -> dict:
    return {
        "client": mock_client,
        "rsids": ["rs1", "rs2", "rs3"],
        "formats": ["json"],
        "output_dir": tmp_path,
        "captured_at": datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC),
        "tool_version": "1.8.0",
    }


# ---------------------------------------------------------------------------
# _exit_code_for fallback
# ---------------------------------------------------------------------------


def test_exit_code_for_unmapped_error_falls_back_to_generic() -> None:
    """A bare AaAutoSdrError matches no mapped subclass; fallback is GENERIC."""
    assert _exit_code_for(AaAutoSdrError("boom")) == ExitCode.GENERIC.value


# ---------------------------------------------------------------------------
# progress_callback (the _make_future submit hook)
# ---------------------------------------------------------------------------


def test_progress_callback_invoked_for_every_rsid(base_kwargs: dict) -> None:
    """progress_callback(i, total, rsid) fires once per submitted RSID."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    calls: list[tuple[int, int, str]] = []

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        run_parallel(
            **base_kwargs,
            workers=2,
            progress_callback=lambda i, total, rsid: calls.append((i, total, rsid)),
        )

    assert len(calls) == 3
    assert {rsid for _, _, rsid in calls} == {"rs1", "rs2", "rs3"}
    assert all(total == 3 for _, total, _ in calls)


# ---------------------------------------------------------------------------
# fail_fast branches
# ---------------------------------------------------------------------------


def test_fail_fast_submits_next_on_success_until_iterator_exhausted(base_kwargs: dict) -> None:
    """fail_fast=True, all-success, workers=1: each success submits the next
    RSID until the iterator raises StopIteration."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(
            **{**base_kwargs, "rsids": ["rs1", "rs2", "rs3"]},
            workers=1,
            fail_fast=True,
        )

    assert len(result.successes) == 3
    assert len(result.failures) == 0
    assert {r.rsid for r in result.successes} == {"rs1", "rs2", "rs3"}


def test_fail_fast_failure_callback_invoked(base_kwargs: dict) -> None:
    """fail_fast=True: the AaAutoSdrError branch calls failure_callback."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    seen: list[tuple[int, int, str, str]] = []

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "f1":
            raise ApiError("boom")
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(
            **{**base_kwargs, "rsids": ["f1", "f2"]},
            workers=1,
            fail_fast=True,
            failure_callback=lambda i, total, rsid, msg: seen.append((i, total, rsid, msg)),
        )

    assert seen, "failure_callback was never invoked"
    assert seen[0][2] == "f1"
    assert "boom" in seen[0][3]
    assert any(f.rsid == "f1" for f in result.failures)


def test_fail_fast_cancelled_error_recorded(base_kwargs: dict) -> None:
    """fail_fast=True: a CancelledError from result() is folded into failures."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        raise CancelledError

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(
            **{**base_kwargs, "rsids": ["c1"]},
            workers=1,
            fail_fast=True,
        )

    assert len(result.failures) == 1
    assert result.failures[0].rsid == "c1"
    assert result.failures[0].error_type == "CancelledError"
    assert result.failures[0].exit_code == ExitCode.GENERIC.value


def test_fail_fast_keyboard_interrupt_cancels_pending_and_reraises(base_kwargs: dict) -> None:
    """fail_fast=True: KeyboardInterrupt cancels still-pending futures, then re-raises.

    k1 raises KeyboardInterrupt immediately while k2 stays in-flight, so the
    interrupt handler observes a non-empty pending_set and cancels k2. A timer
    releases k2 so the pool can shut down without hanging.
    """
    import threading

    import aa_auto_sdr.pipeline.workers as workers_mod

    release = threading.Event()

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "k1":
            raise KeyboardInterrupt
        release.wait(timeout=5.0)  # k2 stays pending until released
        return _success_result(rsid)

    timer = threading.Timer(0.3, release.set)
    timer.start()
    try:
        with (
            patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single),
            pytest.raises(KeyboardInterrupt),
        ):
            run_parallel(**{**base_kwargs, "rsids": ["k1", "k2"]}, workers=2, fail_fast=True)
    finally:
        timer.cancel()
        release.set()


# ---------------------------------------------------------------------------
# normal (continue-on-error) branches
# ---------------------------------------------------------------------------


def test_normal_cancelled_error_recorded(base_kwargs: dict) -> None:
    """Normal mode: a CancelledError from result() is recorded as a failure."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        raise CancelledError

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(**{**base_kwargs, "rsids": ["c1"]}, workers=1)

    assert len(result.failures) == 1
    assert result.failures[0].rsid == "c1"
    assert result.failures[0].error_type == "CancelledError"


def test_normal_failure_callback_invoked(base_kwargs: dict) -> None:
    """Normal mode: the AaAutoSdrError branch calls failure_callback."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    seen: list[tuple[int, int, str, str]] = []

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "rs2":
            raise ApiError("network hiccup")
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        run_parallel(
            **base_kwargs,
            workers=2,
            failure_callback=lambda i, total, rsid, msg: seen.append((i, total, rsid, msg)),
        )

    assert seen, "failure_callback was never invoked"
    assert seen[0][2] == "rs2"
    assert "network hiccup" in seen[0][3]


def test_normal_keyboard_interrupt_cancels_and_reraises(base_kwargs: dict) -> None:
    """Normal mode: KeyboardInterrupt propagates after cancelling pending futures."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        raise KeyboardInterrupt

    with (
        patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single),
        pytest.raises(KeyboardInterrupt),
    ):
        run_parallel(**{**base_kwargs, "rsids": ["k1"]}, workers=1)
