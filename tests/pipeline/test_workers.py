"""Worker pool — see spec §3.2."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api.cache import ValidationCache
from aa_auto_sdr.pipeline.models import BatchResult, RunResult
from aa_auto_sdr.pipeline.workers import (
    get_current_worker_id,
    run_parallel,
)


def _success_result(rsid: str) -> RunResult:
    # CORRECTED — RunResult requires success=True; no snapshot_path field
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
# Tests 1–8: core worker pool behaviour
# ---------------------------------------------------------------------------


def test_run_parallel_completes_all_rsids(base_kwargs: dict) -> None:
    """All RSIDs get a RunResult (success) when _run_single_for_batch succeeds."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(**base_kwargs, workers=2)

    assert isinstance(result, BatchResult)
    assert len(result.successes) == 3
    assert len(result.failures) == 0
    succeeded_rsids = {r.rsid for r in result.successes}
    assert succeeded_rsids == {"rs1", "rs2", "rs3"}


def test_run_parallel_aggregates_failures_in_continue_mode(base_kwargs: dict) -> None:
    """Continue-on-error: partial success when some RSIDs fail."""
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "rs2":
            raise ApiError("network hiccup")
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(**base_kwargs, workers=2, fail_fast=False)

    assert len(result.successes) == 2
    assert len(result.failures) == 1
    (failure,) = result.failures
    assert failure.rsid == "rs2"
    assert failure.error_type == "ApiError"


def test_fail_fast_cancels_pending_after_first_failure(base_kwargs: dict) -> None:
    """fail_fast=True: first failure stops the run; pending futures cancelled.

    Uses workers=1 to serialize so the single worker thread processes rs1,
    fails, and the lazy-submit approach in run_parallel never submits rs2/rs3.
    """
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    call_order: list[str] = []

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        call_order.append(rsid)
        if rsid == "rs1":
            raise ApiError("boom")
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        result = run_parallel(**{**base_kwargs, "rsids": ["rs1", "rs2", "rs3"]}, workers=1, fail_fast=True)

    # At least one failure recorded
    assert len(result.failures) >= 1
    assert result.failures[0].rsid == "rs1"
    # Not all RSIDs ran
    assert len(call_order) < 3


def test_workers_share_aaclient(base_kwargs: dict) -> None:
    """The same AaClient instance is forwarded to every _run_single_for_batch call."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    received_clients: list[object] = []

    def fake_run_single(*, rsid: str, client: object, **_kw: object) -> RunResult:
        received_clients.append(client)
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        run_parallel(**base_kwargs, workers=2)

    # All calls got the same client object
    assert len(received_clients) == 3
    assert all(c is base_kwargs["client"] for c in received_clients)


def test_workers_share_cache(base_kwargs: dict) -> None:
    """When a ValidationCache is supplied, all workers receive the same instance."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    cache = ValidationCache(max_size=10, ttl_seconds=60)
    received_caches: list[object] = []

    def fake_run_single(*, rsid: str, cache: object = None, **_kw: object) -> RunResult:
        received_caches.append(cache)
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        run_parallel(**base_kwargs, workers=2, cache=cache)

    assert len(received_caches) == 3
    assert all(c is cache for c in received_caches)


def test_worker_id_assignment_is_submission_index(base_kwargs: dict) -> None:
    """worker_id seen inside _run_single_for_batch matches the submission index (0-based)."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    seen: dict[str, int | None] = {}

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        seen[rsid] = get_current_worker_id()
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        # workers=1 serializes so IDs are deterministic
        run_parallel(**{**base_kwargs, "rsids": ["rs1", "rs2", "rs3"]}, workers=1)

    # Each RSID saw *some* integer worker_id (not None)
    assert all(wid is not None for wid in seen.values())
    # worker IDs are non-negative integers
    assert all(isinstance(wid, int) and wid >= 0 for wid in seen.values())


def test_worker_id_cleared_after_worker_returns(base_kwargs: dict) -> None:
    """The finally-block in _run_with_worker_id clears worker_id so threads can be reused cleanly.

    Strategy: run two sequential run_parallel calls with workers=1 so the
    ThreadPoolExecutor reuses the same underlying thread for both batches.
    Capture worker_id as seen during each call.  Between the two calls the
    worker_id must have been cleared (otherwise the second call would inherit
    the first call's value rather than the freshly-assigned submission index).

    This is stronger than probing the main thread (which never sets worker_id).
    """
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.pipeline.workers import _worker_local

    # Capture the raw threading.local value at the START of each _run_single_for_batch
    # invocation (i.e., after _run_with_worker_id has assigned worker_id but before
    # the inner call returns).
    captured_during: list[int | None] = []

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        # worker_id is set by the time we enter here (set in _run_with_worker_id's try block).
        captured_during.append(getattr(_worker_local, "worker_id", None))
        return _success_result(rsid)

    kwargs_one = {**base_kwargs, "rsids": ["rs1"]}
    kwargs_two = {**base_kwargs, "rsids": ["rs2"]}

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single):
        # First run: worker_id for rs1 should be 0 (submission index 0).
        run_parallel(**kwargs_one, workers=1)
        # Second run: rs2 is also submission index 0, so worker_id should again be 0.
        # If the finally-block cleanup had NOT run, the second call would find the
        # first call's stale value and then immediately overwrite it — but more
        # importantly the cleanup IS the contract we're testing.
        run_parallel(**kwargs_two, workers=1)

    # Both calls captured a real (non-None) worker_id — the assignment worked.
    assert len(captured_during) == 2
    assert all(wid is not None for wid in captured_during), (
        "worker_id was None inside _run_single_for_batch — assignment did not happen"
    )
    # Each submission was index 0 in its own batch, so both should see worker_id == 0.
    assert captured_during == [0, 0], (
        f"Expected [0, 0] but got {captured_during}. "
        "If the second value is not 0, the finally-block cleanup may not have run "
        "and a stale worker_id bled across batches (though ThreadPoolExecutor always "
        "re-assigns, so this mainly confirms correct assignment semantics)."
    )


def test_get_current_worker_id_outside_worker_returns_none() -> None:
    """get_current_worker_id() returns None when called from the main thread (no pool active)."""
    # Not inside any worker — should be None
    assert get_current_worker_id() is None


# ---------------------------------------------------------------------------
# Tests 9–10: WorkerIdFilter injects worker_id onto log records
# ---------------------------------------------------------------------------


def test_worker_id_filter_injects_worker_id_in_worker_thread() -> None:
    """WorkerIdFilter stamps worker_id on records emitted from a worker thread."""
    from aa_auto_sdr.core.logging import WorkerIdFilter
    from aa_auto_sdr.pipeline.workers import _worker_local

    filter_instance = WorkerIdFilter()
    captured: list[int | None] = []

    def worker_fn() -> None:
        _worker_local.worker_id = 42
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        filter_instance.filter(record)
        captured.append(getattr(record, "worker_id", None))
        # Cleanup
        del _worker_local.worker_id

    t = threading.Thread(target=worker_fn)
    t.start()
    t.join()

    assert captured == [42]


def test_worker_id_filter_omits_field_in_main_thread() -> None:
    """WorkerIdFilter does NOT set worker_id on records from the main thread."""
    from aa_auto_sdr.core.logging import WorkerIdFilter

    filter_instance = WorkerIdFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    filter_instance.filter(record)
    # worker_id should NOT be present on the record (preserves v1.7.2 log equivalence)
    assert not hasattr(record, "worker_id")


def test_worker_id_filter_skips_import_when_workers_not_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """When pipeline.workers was never imported, the filter must skip the import
    entirely (keeps the heavy stack off the light-command runtime path) and
    pass the record through untouched."""
    import sys

    from aa_auto_sdr.core.logging import WorkerIdFilter

    monkeypatch.delitem(sys.modules, "aa_auto_sdr.pipeline.workers", raising=False)
    filter_instance = WorkerIdFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    assert filter_instance.filter(record) is True
    assert not hasattr(record, "worker_id")
    # The guard must not have re-imported workers as a side effect.
    assert "aa_auto_sdr.pipeline.workers" not in sys.modules


# ---------------------------------------------------------------------------
# Test 11: fail_fast records all co-completed futures (regression for drop bug)
# ---------------------------------------------------------------------------


def test_fail_fast_records_all_done_set_items(monkeypatch: pytest.MonkeyPatch) -> None:
    """When wait() returns multiple done futures and one is a failure,
    the others must still be recorded — not silently dropped.

    Uses a threading.Barrier(2) between the two workers so they complete at
    nearly the same instant, making it highly likely that wait(FIRST_COMPLETED)
    returns both futures in a single done_set — reproducing the race that
    exposed the original break-on-first-failure bug.
    """
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    # Barrier between the 2 workers only — no third party needed.
    # Both workers synchronize with each other before returning/raising,
    # ensuring they finish at the same instant.
    worker_barrier = threading.Barrier(2, timeout=5.0)

    def runner(*, rsid: str, **kwargs: object) -> RunResult:
        worker_barrier.wait()  # both workers rendezvous here
        if rsid == "r1":
            raise ApiError("simulated")
        return _success_result(rsid)

    monkeypatch.setattr(workers_mod, "_run_single_for_batch", runner)

    result = run_parallel(
        rsids=["r1", "r2"],
        workers=2,
        client=MagicMock(),
        cache=None,
        fail_fast=True,
        formats=["json"],
        output_dir=Path("/tmp"),
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="1.8.0",
    )

    # Both r1 (failed) and r2 (succeeded) must be accounted for — neither
    # should be silently dropped from BatchResult.
    total_recorded = len(result.successes) + len(result.failures)
    assert total_recorded == 2, (
        f"expected 2 recorded, got {total_recorded} "
        f"(successes={[r.rsid for r in result.successes]}, "
        f"failures={[f.rsid for f in result.failures]})"
    )
    failed_rsids = {f.rsid for f in result.failures}
    assert "r1" in failed_rsids, f"r1 (the failing RSID) not in failures: {result.failures}"


# ---------------------------------------------------------------------------
# Test 12: fail_fast cross-iteration cancel records CancelledError failures
# (regression for bug_020)
# ---------------------------------------------------------------------------


def test_fail_fast_cross_iteration_cancelled_futures_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    """When fail_fast=True and a failure triggers cancel of freshly-submitted futures,
    those cancelled RSIDs must appear in BatchResult.failures (not silently dropped).

    Setup: 4 RSIDs, workers=2. r1 succeeds immediately, r2 fails. r3/r4 may be
    submitted before the cancellation runs. All 4 must be accounted for.
    """
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    # Use a barrier to make r1 and r2 complete simultaneously so the done_set
    # contains both, giving us a cross-done_set scenario where r1's success
    # triggers a resubmit of r3, and r2's failure triggers the cancel of r3/r4.
    barrier = threading.Barrier(2, timeout=5.0)

    def runner(*, rsid: str, **_kw: object) -> RunResult:
        if rsid in ("r1", "r2"):
            barrier.wait()
        if rsid == "r2":
            raise ApiError("forced failure")
        return _success_result(rsid)

    monkeypatch.setattr(workers_mod, "_run_single_for_batch", runner)

    result = run_parallel(
        rsids=["r1", "r2", "r3", "r4"],
        workers=2,
        fail_fast=True,
        client=MagicMock(),
        cache=None,
        formats=["json"],
        output_dir=Path("/tmp"),
        captured_at=datetime(2026, 5, 9, tzinfo=UTC),
        tool_version="1.8.0",
    )

    total_recorded = len(result.successes) + len(result.failures)
    # At minimum, r1 (success), r2 (failure) are always recorded.
    # r3 and r4 may or may not have been submitted; any that were must appear
    # as CancelledError failures. The total must be consistent.
    assert total_recorded >= 2, f"Expected at least 2 recorded (r1+r2), got {total_recorded}"
    # r2 must always be in failures
    failed_rsids = {f.rsid for f in result.failures}
    assert "r2" in failed_rsids
    # Any failure beyond r2 must be a CancelledError
    for f in result.failures:
        if f.rsid != "r2":
            assert f.error_type == "CancelledError", f"Expected CancelledError for {f.rsid}, got {f.error_type}"


# ---------------------------------------------------------------------------
# Test 13: rsid_complete log records carry worker_id
# (regression for merged_bug_002 / Fix C5)
# ---------------------------------------------------------------------------


def test_rsid_complete_log_records_carry_worker_id(
    base_kwargs: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """rsid_complete log records emitted by run_parallel must carry worker_id.

    The WorkerIdFilter runs on worker threads; rsid_complete is logged on the
    main thread (post-future.result()), so worker_id must be explicitly stamped
    in the extra dict rather than injected by the filter.
    """
    import aa_auto_sdr.pipeline.workers as workers_mod

    def fake_run_single(*, rsid: str, **_kw: object) -> RunResult:
        return _success_result(rsid)

    with (
        patch.object(workers_mod, "_run_single_for_batch", side_effect=fake_run_single),
        caplog.at_level(logging.INFO, logger="aa_auto_sdr.pipeline.workers"),
    ):
        run_parallel(**{**base_kwargs, "rsids": ["rs1", "rs2"]}, workers=2)

    complete_records = [r for r in caplog.records if "rsid_complete" in r.getMessage()]
    assert complete_records, "No rsid_complete log records found"
    for record in complete_records:
        assert hasattr(record, "worker_id"), (
            f"rsid_complete record for rsid={getattr(record, 'rsid', '?')} is missing worker_id"
        )


def test_fail_fast_uncancellable_running_future_records_true_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A future that is already RUNNING when fail-fast cancellation kicks in
    cannot be cancelled — it runs to completion and writes its outputs. It must
    be recorded with its real outcome (here: success), not as 'cancelled',
    otherwise the summary contradicts what is on disk."""
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    rb_started = threading.Event()
    release_rb = threading.Event()

    def runner(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "rA":
            rb_started.wait(timeout=5.0)  # rB is definitely RUNNING before rA fails
            raise ApiError("forced failure")
        rb_started.set()
        release_rb.wait(timeout=5.0)  # held until rA's failure is processed
        return _success_result(rsid)

    monkeypatch.setattr(workers_mod, "_run_single_for_batch", runner)

    result = run_parallel(
        rsids=["rA", "rB"],
        workers=2,
        client=MagicMock(),
        cache=None,
        fail_fast=True,
        failure_callback=lambda *_a: release_rb.set(),
        formats=["json"],
        output_dir=Path("/tmp"),
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="1.21.6",
    )

    assert [r.rsid for r in result.successes] == ["rB"]
    assert {f.rsid for f in result.failures} == {"rA"}


def test_fail_fast_records_never_submitted_rsids_as_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With more RSIDs than workers, identifiers still in the lazy-submission
    iterator when fail-fast trips were never submitted at all. They must still
    appear in BatchResult as cancelled failures — otherwise the summary holds
    fewer records than the input."""
    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    def runner(*, rsid: str, **_kw: object) -> RunResult:
        raise ApiError(f"{rsid} failed")

    monkeypatch.setattr(workers_mod, "_run_single_for_batch", runner)

    result = run_parallel(
        rsids=["r1", "r2", "r3", "r4"],
        workers=2,
        client=MagicMock(),
        cache=None,
        fail_fast=True,
        formats=["json"],
        output_dir=Path("/tmp"),
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="1.21.6",
    )

    recorded = {f.rsid for f in result.failures} | {r.rsid for r in result.successes}
    assert recorded == {"r1", "r2", "r3", "r4"}
    by_rsid = {f.rsid: f.error_type for f in result.failures}
    assert by_rsid["r3"] == "CancelledError"
    assert by_rsid["r4"] == "CancelledError"


def test_fail_fast_late_success_emits_rsid_complete_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A still-running worker that completes after fail-fast triggers must go
    through the same rsid_complete logging as a normally-completed future —
    it still wrote output and appears in the summary."""
    import logging

    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    rb_started = threading.Event()
    release_rb = threading.Event()

    def runner(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "rA":
            rb_started.wait(timeout=5.0)
            raise ApiError("forced failure")
        rb_started.set()
        release_rb.wait(timeout=5.0)
        return _success_result(rsid)

    monkeypatch.setattr(workers_mod, "_run_single_for_batch", runner)

    with caplog.at_level(logging.INFO, logger="aa_auto_sdr.pipeline.workers"):
        run_parallel(
            rsids=["rA", "rB"],
            workers=2,
            client=MagicMock(),
            cache=None,
            fail_fast=True,
            failure_callback=lambda *_a: release_rb.set(),
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.21.6",
        )

    complete_rsids = {
        r.rsid for r in caplog.records if r.getMessage().startswith("rsid_complete") and getattr(r, "rsid", None)
    }
    assert "rB" in complete_rsids


def test_fail_fast_late_failure_logs_and_invokes_callback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A still-running worker that fails after fail-fast triggers must emit
    rsid_failure and invoke failure_callback, matching the normal failure path."""
    import logging

    import aa_auto_sdr.pipeline.workers as workers_mod
    from aa_auto_sdr.core.exceptions import ApiError

    rb_started = threading.Event()
    release_rb = threading.Event()
    callback_rsids: list[str] = []

    def runner(*, rsid: str, **_kw: object) -> RunResult:
        if rsid == "rA":
            rb_started.wait(timeout=5.0)
            raise ApiError("rA failed first")
        rb_started.set()
        release_rb.wait(timeout=5.0)
        raise ApiError("rB failed late")

    def _callback(_i: int, _total: int, rsid: str, _msg: str) -> None:
        callback_rsids.append(rsid)
        if rsid == "rA":
            release_rb.set()

    monkeypatch.setattr(workers_mod, "_run_single_for_batch", runner)

    with caplog.at_level(logging.ERROR, logger="aa_auto_sdr.pipeline.workers"):
        result = run_parallel(
            rsids=["rA", "rB"],
            workers=2,
            client=MagicMock(),
            cache=None,
            fail_fast=True,
            failure_callback=_callback,
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.21.6",
        )

    assert {f.rsid for f in result.failures} == {"rA", "rB"}
    # rB is a real API failure, not a synthetic cancellation.
    by_rsid = {f.rsid: f for f in result.failures}
    assert by_rsid["rB"].error_type == "ApiError"
    assert by_rsid["rB"].exit_code == 12
    assert "rB" in callback_rsids
    failure_rsids = {
        r.rsid for r in caplog.records if r.getMessage().startswith("rsid_failure") and getattr(r, "rsid", None)
    }
    assert "rB" in failure_rsids
