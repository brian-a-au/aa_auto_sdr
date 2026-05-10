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
