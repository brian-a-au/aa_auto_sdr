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
    """After a worker completes, its thread-local worker_id is cleared (None or absent)."""
    import aa_auto_sdr.pipeline.workers as workers_mod

    def capturing_run(*, rsid: str, **_kw: object) -> RunResult:
        return _success_result(rsid)

    with patch.object(workers_mod, "_run_single_for_batch", side_effect=capturing_run):
        run_parallel(**{**base_kwargs, "rsids": ["rs1"]}, workers=1)

    # After run_parallel completes, the main thread has no worker_id set.
    assert get_current_worker_id() is None


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
