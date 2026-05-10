"""run_one_cycle / run_watch_loop — pure orchestrator (no I/O)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aa_auto_sdr.pipeline.watch import (
    CycleResult,
    StopToken,
    WatchContext,
)


class TestStopToken:
    def test_initial_state_not_set(self) -> None:
        token = StopToken()
        assert token.is_set() is False

    def test_set_then_is_set_true(self) -> None:
        token = StopToken()
        token.set()
        assert token.is_set() is True

    def test_wraps_threading_event(self) -> None:
        token = StopToken()
        # threading.Event-backed implementation; assert the underlying object exists.
        assert hasattr(token, "_event")
        assert isinstance(token._event, threading.Event)


class TestCycleResult:
    def test_baseline_constructor(self) -> None:
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        r = CycleResult.baseline(
            rsid="rs_a",
            snapshot_path=Path("/tmp/snap.json"),
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        assert r.kind == "baseline"
        assert r.rsid == "rs_a"
        assert r.snapshot_path == Path("/tmp/snap.json")
        assert r.diff is None
        assert r.error is None

    def test_diffed_constructor(self) -> None:
        from aa_auto_sdr.snapshot.models import DiffReport

        diff = DiffReport(
            a_rsid="rs_a",
            b_rsid="rs_a",
            a_captured_at="2026-05-10T13:00:00Z",
            b_captured_at="2026-05-10T14:00:00Z",
            a_tool_version="1.14.0",
            b_tool_version="1.14.0",
        )
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        r = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/snap.json"),
            diff=diff,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        assert r.kind == "diffed"
        assert r.diff is diff
        assert r.error is None

    def test_fetch_error_constructor(self) -> None:
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        err = RuntimeError("503")
        r = CycleResult.fetch_error(
            rsid="rs_a",
            error=err,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        assert r.kind == "fetch_error"
        assert r.error is err
        assert r.snapshot_path is None
        assert r.diff is None


class TestWatchContext:
    def test_constructible_with_required_collaborators(self) -> None:
        # Verify the dataclass shape — collaborators are exercised in later tests.
        @dataclass
        class FakeFetcher:
            def fetch_snapshot(self, rsid: str) -> dict: ...

        @dataclass
        class FakeStore:
            def latest(self, rsid: str) -> dict | None: ...
            def save(self, rsid: str, doc) -> tuple[Path, dict]: ...

        @dataclass
        class FakeClock:
            def utcnow(self) -> datetime: ...

        @dataclass
        class FakeSleeper:
            def sleep(self, seconds: float) -> None: ...

        @dataclass
        class FakeEmitter:
            def emit(self, payload: dict) -> None: ...

        ctx = WatchContext(
            fetcher=FakeFetcher(),
            snapshot_store=FakeStore(),
            clock=FakeClock(),
            sleeper=FakeSleeper(),
            emitter=FakeEmitter(),
            ignore_fields=frozenset(),
            extended_fields=False,
        )
        assert ctx.fetcher is not None
        assert ctx.extended_fields is False
