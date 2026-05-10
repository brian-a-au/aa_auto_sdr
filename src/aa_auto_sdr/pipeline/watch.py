"""Watch-mode loop orchestrator (pure — no I/O).

Two entry points (added in later tasks):

* `run_one_cycle` — per-RSID work (fetch → snapshot → diff). Pure-ish; depends
  on the injected `WatchContext` collaborators.
* `run_watch_loop` — the driver. Iterates RSIDs each cycle, calls the gating
  helpers, and sleeps via the injected sleeper. Polls `StopToken` between
  RSIDs and inside the sleep so SIGINT feels responsive.

All real I/O (network, filesystem, signal handlers, wall-clock sleep) lives
in `cli/commands/watch.py`. This module is fully unit-testable with fakes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from aa_auto_sdr.snapshot.models import DiffReport

# --- Stop token ------------------------------------------------------------


class StopToken:
    """A thread-safe stop signal. Set from a signal handler; polled by the loop."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        """Block up to `timeout` seconds. Returns True if set during the wait."""
        return self._event.wait(timeout=timeout)


# --- Collaborator protocols ------------------------------------------------


class Fetcher(Protocol):
    def fetch_snapshot(self, rsid: str) -> Any: ...


class SnapshotStore(Protocol):
    def latest(self, rsid: str) -> dict[str, Any] | None: ...

    def save(self, rsid: str, doc: Any) -> tuple[Path, dict[str, Any]]:
        """Persist the document and return (path, envelope_dict).

        The envelope is the canonical shape compare() consumes; returning it
        alongside the path lets the orchestrator avoid a re-read of the file
        it just wrote. The real adapter (cli/commands/watch.py) calls
        save_snapshot + load_snapshot to populate both."""
        ...


class Clock(Protocol):
    def utcnow(self) -> datetime: ...


class Sleeper(Protocol):
    def sleep(self, seconds: float) -> None: ...


class Emitter(Protocol):
    def emit(self, payload: dict[str, Any]) -> None: ...


# --- Context ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WatchContext:
    """Injected collaborators + per-loop options. Built once per `--watch` invocation."""

    fetcher: Fetcher
    snapshot_store: SnapshotStore
    clock: Clock
    sleeper: Sleeper
    emitter: Emitter
    ignore_fields: frozenset[str] = field(default_factory=frozenset)
    extended_fields: bool = False


# --- Cycle result ----------------------------------------------------------


CycleKind = Literal["baseline", "diffed", "fetch_error"]


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Outcome of running one RSID through one cycle. Tagged union over `kind`."""

    kind: CycleKind
    rsid: str
    started_at: datetime
    ended_at: datetime
    snapshot_path: Path | None = None
    diff: DiffReport | None = None
    error: BaseException | None = None

    @classmethod
    def baseline(
        cls,
        *,
        rsid: str,
        snapshot_path: Path,
        started_at: datetime,
        ended_at: datetime,
    ) -> CycleResult:
        return cls(
            kind="baseline",
            rsid=rsid,
            started_at=started_at,
            ended_at=ended_at,
            snapshot_path=snapshot_path,
        )

    @classmethod
    def diffed(
        cls,
        *,
        rsid: str,
        snapshot_path: Path,
        diff: DiffReport,
        started_at: datetime,
        ended_at: datetime,
    ) -> CycleResult:
        return cls(
            kind="diffed",
            rsid=rsid,
            started_at=started_at,
            ended_at=ended_at,
            snapshot_path=snapshot_path,
            diff=diff,
        )

    @classmethod
    def fetch_error(
        cls,
        *,
        rsid: str,
        error: BaseException,
        started_at: datetime,
        ended_at: datetime,
    ) -> CycleResult:
        return cls(
            kind="fetch_error",
            rsid=rsid,
            started_at=started_at,
            ended_at=ended_at,
            error=error,
        )


# --- compare() import + run_one_cycle ------------------------------------

from aa_auto_sdr.snapshot.comparator import compare  # noqa: E402 — import-after-types


def run_one_cycle(*, rsid: str, ctx: WatchContext) -> CycleResult:
    """Run a single watch cycle for one RSID.

    Steps:
      1. Read the prior snapshot envelope dict from the store (None on first cycle).
      2. Fetch the current state via the injected fetcher. On any non-control-flow
         exception, return a `fetch_error` result without saving anything.
         KeyboardInterrupt and SystemExit propagate so signal handlers can drive a
         clean shutdown.
      3. Save the current snapshot. `save()` returns `(path, envelope_dict)` — the
         envelope is the canonical shape compare() expects, so we get it back
         in-memory without a re-read.
      4. If prior was None, return a `baseline` result (no diff).
      5. Otherwise, diff prior_envelope vs current_envelope and return a `diffed`
         result. Both sides are dicts — matches the shape used by --diff and
         v1.13 trending.
    """
    started_at = ctx.clock.utcnow()
    prev = ctx.snapshot_store.latest(rsid)

    try:
        current_doc = ctx.fetcher.fetch_snapshot(rsid)
    except KeyboardInterrupt, SystemExit:
        raise
    except Exception as e:  # cycle errors are non-fatal to the loop
        return CycleResult.fetch_error(
            rsid=rsid,
            error=e,
            started_at=started_at,
            ended_at=ctx.clock.utcnow(),
        )

    snapshot_path, current_envelope = ctx.snapshot_store.save(rsid, current_doc)

    if prev is None:
        return CycleResult.baseline(
            rsid=rsid,
            snapshot_path=snapshot_path,
            started_at=started_at,
            ended_at=ctx.clock.utcnow(),
        )

    diff = compare(
        a=prev,
        b=current_envelope,
        ignore_fields=ctx.ignore_fields,
        extended_fields=ctx.extended_fields,
    )
    return CycleResult.diffed(
        rsid=rsid,
        snapshot_path=snapshot_path,
        diff=diff,
        started_at=started_at,
        ended_at=ctx.clock.utcnow(),
    )


# --- emit gating + payload -------------------------------------------------

from aa_auto_sdr.core.logging import redact_text  # noqa: E402 — scrubs error strings before emit
from aa_auto_sdr.output.watch_event import WATCH_EVENT_SCHEMA  # noqa: E402


def _total_changes(diff: DiffReport) -> int:
    """Sum added + removed + modified across all component types."""
    return sum(len(c.added) + len(c.removed) + len(c.modified) for c in diff.components)


def _should_emit(result: CycleResult, *, threshold: int) -> bool:
    """Decide whether this cycle's result should be emitted as an NDJSON event.

    Rules:
      * baseline / fetch_error → always emit.
      * diffed → emit when total_changes >= threshold. threshold=0 means emit
                 every cycle including zero-change (heartbeat).
    """
    if result.kind in ("baseline", "fetch_error"):
        return True
    assert result.diff is not None  # type guard — kind == "diffed"
    if threshold == 0:
        return True
    return _total_changes(result.diff) >= threshold


def _iso_z(ts: datetime) -> str:
    """Format a UTC datetime as Z-suffixed ISO-8601 (matches snapshot envelope)."""
    return ts.isoformat().replace("+00:00", "Z")


def _event_name(kind: CycleKind) -> str:
    return {"baseline": "baseline", "diffed": "change", "fetch_error": "error"}[kind]


def _diff_summary(diff: DiffReport) -> dict[str, Any]:
    """Aggregate counts (added/removed/modified/unchanged) + per-component-type breakdown."""
    added = removed = modified = unchanged = 0
    by_type: dict[str, dict[str, int]] = {}
    for c in diff.components:
        a, r, m = len(c.added), len(c.removed), len(c.modified)
        added += a
        removed += r
        modified += m
        unchanged += c.unchanged_count
        by_type[c.component_type] = {"added": a, "removed": r, "modified": m}
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "by_type": by_type,
    }


def _event_payload(result: CycleResult, *, cycle_n: int) -> dict[str, Any]:
    """Build the NDJSON event payload for a CycleResult.

    Timestamps use Z-suffix. The `error` field is passed through
    `core.logging.redact_text` so tokens / org IDs in API errors don't leak.
    """
    base: dict[str, Any] = {
        "schema": WATCH_EVENT_SCHEMA,
        "event": _event_name(result.kind),
        "cycle": cycle_n,
        "rsid": result.rsid,
        "started_at": _iso_z(result.started_at),
        "ended_at": _iso_z(result.ended_at),
    }
    if result.kind == "baseline":
        base["snapshot_path"] = str(result.snapshot_path)
        return base
    if result.kind == "fetch_error":
        err = result.error
        base["error_type"] = type(err).__name__ if err is not None else "Unknown"
        base["error"] = redact_text(str(err)) if err is not None else ""
        return base
    # diffed
    assert result.diff is not None
    base["snapshot_path"] = str(result.snapshot_path)
    base["summary"] = _diff_summary(result.diff)
    return base


# --- loop driver -----------------------------------------------------------

from datetime import timedelta  # noqa: E402

from aa_auto_sdr.core.exit_codes import ExitCode  # noqa: E402


def _interruptible_sleep(
    stop: StopToken,
    *,
    until: datetime,
    sleeper: Sleeper,
    clock: Clock,
    poll_seconds: float = 0.25,
) -> None:
    """Sleep until `until` or until `stop` is set, whichever comes first.

    Polls `stop.is_set()` every `poll_seconds` so SIGINT is honored within a
    quarter-second by default.
    """
    while not stop.is_set():
        now = clock.utcnow()
        if now >= until:
            return
        remaining = (until - now).total_seconds()
        slice_ = min(poll_seconds, remaining)
        if slice_ <= 0:
            return
        sleeper.sleep(slice_)


def run_watch_loop(
    *,
    ctx: WatchContext,
    rsids: list[str] | tuple[str, ...],
    interval: timedelta,
    threshold: int,
    stop: StopToken,
    max_cycles: int | None = None,
) -> ExitCode:
    """Drive the watch loop.

    First cycle runs immediately (no leading sleep). Subsequent cycles sleep
    until `cycle_start + interval`. Returns when:
      * `stop` is set (SIGINT/SIGTERM), or
      * `max_cycles` cycles have completed.

    Per-cycle errors (`fetch_error` results) emit an `error` event and the
    loop continues. SIGINT received between RSIDs aborts the current cycle.
    """
    cycle_n = 0
    while not stop.is_set():
        cycle_started = ctx.clock.utcnow()
        for rsid in rsids:
            if stop.is_set():
                break
            result = run_one_cycle(rsid=rsid, ctx=ctx)
            if _should_emit(result, threshold=threshold):
                ctx.emitter.emit(_event_payload(result, cycle_n=cycle_n))
        cycle_n += 1
        if max_cycles is not None and cycle_n >= max_cycles:
            return ExitCode.OK
        if stop.is_set():
            break
        _interruptible_sleep(
            stop,
            until=cycle_started + interval,
            sleeper=ctx.sleeper,
            clock=ctx.clock,
        )
    return ExitCode.OK
