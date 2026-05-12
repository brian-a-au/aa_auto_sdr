"""run_one_cycle / run_watch_loop — pure orchestrator (no I/O)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from dataclasses import dataclass as _dc
from dataclasses import field as _f
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any as _Any

import pytest

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.watch_event import WATCH_EVENT_SCHEMA
from aa_auto_sdr.pipeline.watch import (
    CycleResult,
    StopToken,
    WatchContext,
    _event_payload,
    _interruptible_sleep,
    _should_emit,
    run_one_cycle,
    run_watch_loop,
)
from aa_auto_sdr.snapshot.models import AddedRemovedItem, ComponentDiff, DiffReport


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


# --- run_one_cycle ---------------------------------------------------------


@_dc
class _FakeClock:
    """Deterministic clock — each `utcnow()` advances by 1 second."""

    _now: datetime = _f(default_factory=lambda: datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC))

    def utcnow(self) -> datetime:
        out = self._now
        self._now = self._now + timedelta(seconds=1)
        return out


@_dc
class _FakeFetcher:
    rsid_to_doc: dict[str, _Any] = _f(default_factory=dict)
    raise_for: dict[str, BaseException] = _f(default_factory=dict)
    calls: list[str] = _f(default_factory=list)

    def fetch_snapshot(self, rsid: str) -> _Any:
        self.calls.append(rsid)
        if rsid in self.raise_for:
            raise self.raise_for[rsid]
        return self.rsid_to_doc.get(rsid, {"rsid": rsid})


@_dc
class _FakeStore:
    """Fake snapshot store. `save()` returns `(path, envelope_dict)` to mirror
    the real store contract: the envelope is what compare() consumes on the
    next cycle, and exposing it inline avoids a re-read from disk."""

    latest_by_rsid: dict[str, dict | None] = _f(default_factory=dict)
    saved: list[tuple[str, _Any]] = _f(default_factory=list)

    def latest(self, rsid: str) -> dict | None:
        return self.latest_by_rsid.get(rsid)

    def save(self, rsid: str, doc: _Any) -> tuple[Path, dict]:
        self.saved.append((rsid, doc))
        path = Path(f"/tmp/{rsid}/{len(self.saved)}.json")
        envelope = {
            "rsid": rsid,
            "_seq": len(self.saved),
            "_doc": doc,
            # minimal keys required by snapshot.comparator.compare()
            "captured_at": "2026-05-10T14:00:00Z",
            "tool_version": "1.14.0",
            "components": {"report_suite": {}},
        }
        self.latest_by_rsid[rsid] = envelope
        return path, envelope


@_dc
class _FakeSleeper:
    calls: list[float] = _f(default_factory=list)

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


@_dc
class _FakeEmitter:
    events: list[dict] = _f(default_factory=list)

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


def _ctx(**overrides) -> WatchContext:
    defaults: dict[str, _Any] = {
        "fetcher": _FakeFetcher(),
        "snapshot_store": _FakeStore(),
        "clock": _FakeClock(),
        "sleeper": _FakeSleeper(),
        "emitter": _FakeEmitter(),
        "ignore_fields": frozenset(),
        "extended_fields": False,
    }
    defaults.update(overrides)
    return WatchContext(**defaults)


class TestRunOneCycle:
    def test_baseline_when_no_prior_snapshot(self) -> None:
        ctx = _ctx()
        result = run_one_cycle(rsid="rs_a", ctx=ctx)
        assert result.kind == "baseline"
        assert result.rsid == "rs_a"
        assert result.snapshot_path is not None
        assert result.diff is None
        assert ctx.snapshot_store.saved == [("rs_a", {"rsid": "rs_a"})]

    def test_diffed_when_prior_snapshot_exists(self, monkeypatch) -> None:
        from aa_auto_sdr.pipeline import watch as watch_mod

        prior_envelope = {"some": "envelope"}
        store = _FakeStore(latest_by_rsid={"rs_a": prior_envelope})
        fetcher = _FakeFetcher(rsid_to_doc={"rs_a": {"current": True}})
        expected_diff = DiffReport(
            a_rsid="rs_a",
            b_rsid="rs_a",
            a_captured_at="X",
            b_captured_at="Y",
            a_tool_version="1.14.0",
            b_tool_version="1.14.0",
            components=[ComponentDiff(component_type="dimensions")],
        )
        captured: dict = {}

        def fake_compare(*, a, b, ignore_fields, extended_fields):
            captured["a"] = a
            captured["b"] = b
            captured["ignore_fields"] = ignore_fields
            captured["extended_fields"] = extended_fields
            return expected_diff

        monkeypatch.setattr(watch_mod, "compare", fake_compare)

        ctx = _ctx(snapshot_store=store, fetcher=fetcher)
        result = run_one_cycle(rsid="rs_a", ctx=ctx)

        assert result.kind == "diffed"
        assert result.diff is expected_diff
        # `a` is the prior envelope; `b` is the envelope returned from store.save() —
        # NOT the raw doc from fetcher.fetch_snapshot().
        assert captured["a"] is prior_envelope
        assert captured["b"]["rsid"] == "rs_a"
        assert captured["b"]["_doc"] == {"current": True}

    def test_fetch_error_returns_fetch_error_variant(self) -> None:
        boom = RuntimeError("503 Service Unavailable")
        fetcher = _FakeFetcher(raise_for={"rs_a": boom})
        ctx = _ctx(fetcher=fetcher)
        result = run_one_cycle(rsid="rs_a", ctx=ctx)
        assert result.kind == "fetch_error"
        assert result.error is boom
        assert ctx.snapshot_store.saved == []  # no save on fetch failure

    def test_unforeseen_exception_returns_fetch_error_variant(self) -> None:
        boom = ValueError("unexpected garbage")
        fetcher = _FakeFetcher(raise_for={"rs_a": boom})
        ctx = _ctx(fetcher=fetcher)
        result = run_one_cycle(rsid="rs_a", ctx=ctx)
        assert result.kind == "fetch_error"
        assert result.error is boom

    def test_keyboard_interrupt_propagates(self) -> None:
        fetcher = _FakeFetcher(raise_for={"rs_a": KeyboardInterrupt()})
        ctx = _ctx(fetcher=fetcher)
        with pytest.raises(KeyboardInterrupt):
            run_one_cycle(rsid="rs_a", ctx=ctx)

    def test_snapshot_always_saved_when_fetch_succeeds(self) -> None:
        ctx = _ctx()
        run_one_cycle(rsid="rs_a", ctx=ctx)
        assert len(ctx.snapshot_store.saved) == 1


# --- gating + payload ------------------------------------------------------


def _diff_with_counts(added: int, removed: int, modified: int) -> DiffReport:
    """Build a DiffReport whose total sums to (added+removed+modified)."""
    return DiffReport(
        a_rsid="rs_a",
        b_rsid="rs_a",
        a_captured_at="X",
        b_captured_at="Y",
        a_tool_version="1.14.0",
        b_tool_version="1.14.0",
        components=[
            ComponentDiff(
                component_type="dimensions",
                added=[AddedRemovedItem(id=f"a{i}", name=f"a{i}") for i in range(added)],
                removed=[AddedRemovedItem(id=f"r{i}", name=f"r{i}") for i in range(removed)],
                modified=[],
                unchanged_count=10,
            ),
        ],
    )


class TestShouldEmit:
    def test_baseline_always_emits_regardless_of_threshold(self) -> None:
        r = CycleResult.baseline(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            started_at=datetime(2026, 5, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        assert _should_emit(r, threshold=1) is True
        assert _should_emit(r, threshold=100) is True

    def test_fetch_error_always_emits_regardless_of_threshold(self) -> None:
        r = CycleResult.fetch_error(
            rsid="rs_a",
            error=RuntimeError("x"),
            started_at=datetime(2026, 5, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        assert _should_emit(r, threshold=1) is True
        assert _should_emit(r, threshold=100) is True

    def test_diffed_emits_when_changes_meet_threshold(self) -> None:
        r = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            diff=_diff_with_counts(added=3, removed=0, modified=0),
            started_at=datetime(2026, 5, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        assert _should_emit(r, threshold=1) is True
        assert _should_emit(r, threshold=3) is True
        assert _should_emit(r, threshold=4) is False

    def test_threshold_zero_emits_every_cycle_including_zero_change(self) -> None:
        r = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            diff=_diff_with_counts(added=0, removed=0, modified=0),
            started_at=datetime(2026, 5, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        assert _should_emit(r, threshold=0) is True

    def test_threshold_one_suppresses_zero_change_diffed(self) -> None:
        r = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            diff=_diff_with_counts(added=0, removed=0, modified=0),
            started_at=datetime(2026, 5, 10, tzinfo=UTC),
            ended_at=datetime(2026, 5, 10, tzinfo=UTC),
        )
        assert _should_emit(r, threshold=1) is False


class TestEventPayload:
    def test_baseline_payload_shape(self) -> None:
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        r = CycleResult.baseline(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        p = _event_payload(r, cycle_n=0)
        assert p["schema"] == WATCH_EVENT_SCHEMA
        assert p["event"] == "baseline"
        assert p["cycle"] == 0
        assert p["rsid"] == "rs_a"
        assert p["snapshot_path"] == "/tmp/s.json"
        # Z-suffix matches snapshot envelope `captured_at` convention.
        assert p["started_at"] == "2026-05-10T14:00:00Z"
        assert p["ended_at"] == "2026-05-10T14:00:01Z"

    def test_change_payload_includes_summary(self) -> None:
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        r = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            diff=_diff_with_counts(added=2, removed=1, modified=0),
            started_at=now,
            ended_at=now + timedelta(seconds=2),
        )
        p = _event_payload(r, cycle_n=7)
        assert p["event"] == "change"
        assert p["cycle"] == 7
        s = p["summary"]
        assert s["added"] == 2
        assert s["removed"] == 1
        assert s["modified"] == 0
        assert s["unchanged"] == 10
        assert "by_type" in s
        assert s["by_type"]["dimensions"]["added"] == 2
        assert s["by_type"]["dimensions"]["removed"] == 1

    def test_error_payload_shape(self) -> None:
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        err = RuntimeError("503 Service Unavailable")
        r = CycleResult.fetch_error(
            rsid="rs_a",
            error=err,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        p = _event_payload(r, cycle_n=3)
        assert p["event"] == "error"
        assert p["error_type"] == "RuntimeError"
        assert p["error"] == "503 Service Unavailable"
        assert "snapshot_path" not in p
        assert "summary" not in p

    def test_error_payload_redacts_secrets(self) -> None:
        # AA error messages can carry tokens / org IDs in URLs. The watch
        # stream MUST pass `error` through core.logging.redact_text before emit.
        # We craft an error string containing a Bearer token; the redactor should
        # mask it. Exact mask shape depends on the redactor — assert the raw
        # secret is GONE.
        now = datetime(2026, 5, 10, 14, 0, 0, tzinfo=UTC)
        err = RuntimeError("Bearer abc123def456ghi789 — auth failed")
        r = CycleResult.fetch_error(
            rsid="rs_a",
            error=err,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
        )
        p = _event_payload(r, cycle_n=3)
        # If the redactor doesn't recognize this exact pattern, this test
        # would fail — in which case verify what patterns redact_text DOES
        # match (read core/logging.py) and adjust the test fixture string.
        assert "abc123def456ghi789" not in p["error"], f"Token leaked into watch event: {p['error']!r}"
        assert p["error_type"] == "RuntimeError"


# --- run_watch_loop --------------------------------------------------------


class TestInterruptibleSleep:
    def test_returns_immediately_when_stop_set(self) -> None:
        token = StopToken()
        token.set()
        sleeper = _FakeSleeper()
        clock = _FakeClock()
        until = clock.utcnow() + timedelta(seconds=10)
        _interruptible_sleep(token, until=until, sleeper=sleeper, clock=clock, poll_seconds=0.1)
        # No sleep slices when stop is already set.
        assert sleeper.calls == []

    def test_polls_in_short_intervals_until_stop_or_deadline(self) -> None:
        token = StopToken()
        sleeper = _FakeSleeper()

        @_dc
        class StaticClock:
            """Clock that never advances; sets `stop` after 5 calls."""

            _now: datetime = _f(default_factory=lambda: datetime(2026, 5, 10, tzinfo=UTC))
            calls: list[int] = _f(default_factory=list)

            def utcnow(self) -> datetime:
                self.calls.append(1)
                if len(self.calls) >= 5:
                    token.set()
                return self._now

        clock = StaticClock()
        until = datetime(2026, 5, 10, tzinfo=UTC) + timedelta(seconds=10)
        _interruptible_sleep(token, until=until, sleeper=sleeper, clock=clock, poll_seconds=0.25)
        assert 3 <= len(sleeper.calls) <= 6
        for s in sleeper.calls:
            assert s <= 0.25 + 1e-9


class TestRunWatchLoop:
    def test_first_cycle_runs_immediately_no_sleep_before(self) -> None:
        ctx = _ctx()
        token = StopToken()
        rc, _cycles = run_watch_loop(
            ctx=ctx,
            rsids=["rs_a"],
            interval=timedelta(hours=1),
            threshold=1,
            stop=token,
            max_cycles=1,
        )
        assert rc == ExitCode.OK
        # One baseline emitted, no sleep call (max_cycles=1 exits immediately).
        assert len(ctx.emitter.events) == 1
        assert ctx.emitter.events[0]["event"] == "baseline"
        assert ctx.sleeper.calls == []

    def test_three_cycles_iterate_multiple_rsids(self) -> None:
        ctx = _ctx()
        token = StopToken()
        rc, cycles = run_watch_loop(
            ctx=ctx,
            rsids=["rs_a", "rs_b"],
            interval=timedelta(seconds=0),
            threshold=0,
            stop=token,
            max_cycles=3,
        )
        assert rc == ExitCode.OK
        # 2 rsids × 3 cycles = 6 events (threshold=0 emits every cycle).
        assert len(ctx.emitter.events) == 6
        assert ctx.emitter.events[0]["event"] == "baseline"
        assert ctx.emitter.events[1]["event"] == "baseline"
        for ev in ctx.emitter.events[2:]:
            assert ev["event"] == "change"
        assert cycles == 3  # max_cycles=3 was the terminator

    def test_threshold_gates_change_events(self) -> None:
        ctx = _ctx()
        rc, _cycles = run_watch_loop(
            ctx=ctx,
            rsids=["rs_a"],
            interval=timedelta(seconds=0),
            threshold=1,
            stop=StopToken(),
            max_cycles=3,
        )
        assert rc == ExitCode.OK
        # Cycle 0 baseline emits. Cycles 1-2 are zero-change diffs — threshold=1 suppresses.
        assert len(ctx.emitter.events) == 1
        assert ctx.emitter.events[0]["event"] == "baseline"

    def test_fetch_error_does_not_terminate_loop(self) -> None:
        fetcher = _FakeFetcher(
            raise_for={"rs_a": RuntimeError("boom")},
            rsid_to_doc={"rs_b": {"rsid": "rs_b"}},
        )
        ctx = _ctx(fetcher=fetcher)
        rc, _cycles = run_watch_loop(
            ctx=ctx,
            rsids=["rs_a", "rs_b"],
            interval=timedelta(seconds=0),
            threshold=0,
            stop=StopToken(),
            max_cycles=2,
        )
        assert rc == ExitCode.OK
        events_by_kind = [e["event"] for e in ctx.emitter.events]
        assert events_by_kind.count("error") == 2
        assert events_by_kind.count("baseline") == 1
        assert events_by_kind.count("change") == 1

    def test_stop_token_set_mid_loop_terminates_cleanly(self) -> None:
        ctx = _ctx()
        token = StopToken()
        original_emit = ctx.emitter.emit

        def emit_then_stop(payload: dict) -> None:
            original_emit(payload)
            token.set()

        ctx.emitter.emit = emit_then_stop  # type: ignore[method-assign]
        rc, _cycles = run_watch_loop(
            ctx=ctx,
            rsids=["rs_a", "rs_b"],
            interval=timedelta(seconds=0),
            threshold=0,
            stop=token,
            max_cycles=10,
        )
        assert rc == ExitCode.OK
        # rs_a baseline emits, sets stop. rs_b never runs.
        assert len(ctx.emitter.events) == 1
        assert ctx.emitter.events[0]["rsid"] == "rs_a"

    def test_max_cycles_none_relies_on_stop_token(self) -> None:
        ctx = _ctx()
        token = StopToken()
        original_emit = ctx.emitter.emit

        def emit_then_maybe_stop(payload: dict) -> None:
            original_emit(payload)
            if len(ctx.emitter.events) >= 2:
                token.set()

        ctx.emitter.emit = emit_then_maybe_stop  # type: ignore[method-assign]
        rc, cycles = run_watch_loop(
            ctx=ctx,
            rsids=["rs_a"],
            interval=timedelta(seconds=0),
            threshold=0,
            stop=token,
            max_cycles=None,
        )
        assert rc == ExitCode.OK
        assert len(ctx.emitter.events) == 2
        assert cycles >= 2  # at least the two cycles that emitted events


# --- v1.15.0 git composition ----------------------------------------------

from aa_auto_sdr.snapshot.git import GitOpResult as _GitOpResult  # noqa: E402


def _diff_with_counts_v2(*, added: int, removed: int, modified: int) -> DiffReport:
    """Build a minimal DiffReport with a single 'dimensions' component carrying
    the requested counts.
    """
    return DiffReport(
        a_rsid="rs_a",
        b_rsid="rs_a",
        a_captured_at="2026-05-11T13:00:00Z",
        b_captured_at="2026-05-11T14:00:00Z",
        a_tool_version="1.15.0",
        b_tool_version="1.15.0",
        components=[
            ComponentDiff(
                component_type="dimensions",
                added=[AddedRemovedItem(id=f"a{i}", name=f"a{i}") for i in range(added)],
                removed=[AddedRemovedItem(id=f"r{i}", name=f"r{i}") for i in range(removed)],
                modified=[],
                unchanged_count=0,
            ),
        ],
    )


class TestRunOneCycleGit:
    """run_one_cycle itself no longer calls git_commit_snapshot (P2b refactor).

    Git commits are now done by _maybe_commit, called from run_watch_loop
    AFTER the _should_emit gate. These tests verify that:

      * run_one_cycle always returns git_op=None (the git step moved out).
      * _maybe_commit populates git_op when git_commit=True.
      * _maybe_commit skips git when git_commit=False.
    """

    def test_run_one_cycle_never_populates_git_op(self, monkeypatch) -> None:
        from aa_auto_sdr.pipeline import watch as watch_mod

        ctx = _ctx(
            git_commit=True,
            git_push=False,
            git_message=None,
            snapshot_dir=Path("/tmp/snaps"),
        )

        called: list[int] = []
        monkeypatch.setattr(
            watch_mod,
            "git_commit_snapshot",
            lambda *_a, **_kw: (called.append(1), _GitOpResult(ok=True))[1],
        )

        # After the P2b refactor run_one_cycle never calls git_commit_snapshot.
        cycle = watch_mod.run_one_cycle(rsid="rs_a", ctx=ctx)
        assert cycle.git_op is None
        assert called == [], "git_commit_snapshot must NOT be called from run_one_cycle"

    def test_maybe_commit_populates_git_op_when_git_commit_true(self, monkeypatch) -> None:
        from aa_auto_sdr.pipeline import watch as watch_mod

        ctx = _ctx(
            git_commit=True,
            git_push=False,
            git_message=None,
            snapshot_dir=Path("/tmp/snaps"),
        )

        canned_result = _GitOpResult(
            ok=True,
            committed=True,
            commit_sha="abc1234567" * 4,
        )
        monkeypatch.setattr(watch_mod, "git_commit_snapshot", lambda *_a, **_kw: canned_result)

        base_cycle = watch_mod.run_one_cycle(rsid="rs_a", ctx=ctx)
        assert base_cycle.git_op is None  # not yet populated

        committed_cycle = watch_mod._maybe_commit(ctx, base_cycle, cycle_n=0)
        assert committed_cycle.git_op is canned_result

    def test_maybe_commit_skips_git_when_git_commit_false(self, monkeypatch) -> None:
        from aa_auto_sdr.pipeline import watch as watch_mod

        ctx = _ctx(git_commit=False)

        called: list[int] = []
        monkeypatch.setattr(
            watch_mod,
            "git_commit_snapshot",
            lambda *_a, **_kw: (called.append(1), _GitOpResult(ok=True))[1],
        )

        base_cycle = watch_mod.run_one_cycle(rsid="rs_a", ctx=ctx)
        result = watch_mod._maybe_commit(ctx, base_cycle, cycle_n=0)
        assert result.git_op is None
        assert called == []


class TestEventPayloadGit:
    def test_change_event_includes_git_block_on_success(self) -> None:
        from dataclasses import replace

        from aa_auto_sdr.pipeline.watch import CycleResult, _event_payload

        diff = _diff_with_counts_v2(added=2, removed=0, modified=0)
        git_op = _GitOpResult(
            ok=True,
            committed=True,
            pushed=True,
            commit_sha="x" * 40,
        )
        base = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            diff=diff,
            started_at=datetime(2026, 5, 11, 14, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 11, 14, 0, 1, tzinfo=UTC),
        )
        r = replace(base, git_op=git_op)
        p = _event_payload(r, cycle_n=7)
        assert p["event"] == "change"
        assert p["git"] == {
            "committed": True,
            "commit_sha": "x" * 40,
            "pushed": True,
        }

    def test_change_event_omits_git_block_when_no_git_op(self) -> None:
        from aa_auto_sdr.pipeline.watch import CycleResult, _event_payload

        diff = _diff_with_counts_v2(added=1, removed=0, modified=0)
        r = CycleResult.diffed(
            rsid="rs_a",
            snapshot_path=Path("/tmp/s.json"),
            diff=diff,
            started_at=datetime(2026, 5, 11, 14, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 11, 14, 0, 1, tzinfo=UTC),
        )
        p = _event_payload(r, cycle_n=3)
        assert "git" not in p


class TestWatchCycleFooter:
    """Pin that watch-mode commits carry a `(watch cycle <n>)` footer in the
    auto-generated message, and that user-supplied `git_message` is verbatim.

    Closes the v1.15.0 explicit defer: generate_commit_message accepts
    watch_cycle, but the production caller didn't pass it through.
    """

    def _ctx(self, *, git_message, snapshot_dir):
        from aa_auto_sdr.pipeline.watch import WatchContext

        # Minimal collaborators — _maybe_commit only reads
        # git_commit / git_push / git_message / snapshot_dir.
        class _Stub:
            def utcnow(self):
                from datetime import UTC, datetime

                return datetime.now(UTC)

            def sleep(self, seconds): ...

            def emit(self, payload): ...

            def latest(self, rsid):
                return None

            def save(self, rsid, doc): ...

            def fetch_snapshot(self, rsid): ...

        stub = _Stub()
        return WatchContext(
            fetcher=stub,
            snapshot_store=stub,
            clock=stub,
            sleeper=stub,
            emitter=stub,
            git_commit=True,
            git_push=False,
            git_message=git_message,
            snapshot_dir=snapshot_dir,
        )

    def test_auto_message_includes_watch_cycle_footer(self, monkeypatch, tmp_path) -> None:
        from datetime import UTC, datetime

        from aa_auto_sdr.pipeline import watch as watch_mod
        from aa_auto_sdr.pipeline.watch import CycleResult
        from aa_auto_sdr.snapshot.git import GitOpResult

        captured: dict[str, str | None] = {}

        def _fake_commit(snapshot_dir, *, rsid, message, push):
            captured["message"] = message
            return GitOpResult(
                ok=True,
                committed=True,
                commit_sha="abc123",
                pushed=False,
                error_kind=None,
                error_message=None,
            )

        monkeypatch.setattr(watch_mod, "git_commit_snapshot", _fake_commit)
        ctx = self._ctx(git_message=None, snapshot_dir=tmp_path)
        base = CycleResult.baseline(
            rsid="rs_a",
            snapshot_path=tmp_path / "rs_a" / "snap.json",
            started_at=datetime(2026, 5, 11, 14, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 11, 14, 0, 1, tzinfo=UTC),
        )

        watch_mod._maybe_commit(ctx, base, cycle_n=7)

        assert captured["message"] is not None
        assert captured["message"].rstrip().endswith("(watch cycle 7)")

    def test_user_supplied_git_message_is_verbatim(self, monkeypatch, tmp_path) -> None:
        """--git-message replaces the entire message — no footer appended."""
        from datetime import UTC, datetime

        from aa_auto_sdr.pipeline import watch as watch_mod
        from aa_auto_sdr.pipeline.watch import CycleResult
        from aa_auto_sdr.snapshot.git import GitOpResult

        captured: dict[str, str | None] = {}

        def _fake_commit(snapshot_dir, *, rsid, message, push):
            captured["message"] = message
            return GitOpResult(
                ok=True,
                committed=True,
                commit_sha="abc123",
                pushed=False,
                error_kind=None,
                error_message=None,
            )

        monkeypatch.setattr(watch_mod, "git_commit_snapshot", _fake_commit)
        ctx = self._ctx(git_message="release v2.3", snapshot_dir=tmp_path)
        base = CycleResult.baseline(
            rsid="rs_a",
            snapshot_path=tmp_path / "rs_a" / "snap.json",
            started_at=datetime(2026, 5, 11, 14, 0, 0, tzinfo=UTC),
            ended_at=datetime(2026, 5, 11, 14, 0, 1, tzinfo=UTC),
        )

        watch_mod._maybe_commit(ctx, base, cycle_n=7)

        assert captured["message"] == "release v2.3"
