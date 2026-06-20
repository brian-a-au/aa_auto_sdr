"""--watch command handler.

Wires the pure `pipeline/watch.py` orchestrator to real-world collaborators:
* a fetcher backed by `api/client.py::AaClient` + `sdr/builder.py::build_sdr`
* a snapshot store backed by `snapshot/store.py`
* a wall clock and `time.sleep`
* an emitter writing NDJSON to sys.stdout
* SIGINT/SIGTERM handlers that set a shared StopToken
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aa_auto_sdr.cli.commands._shared import resolve_snapshot_dir
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.watch_event import StdoutEmitter
from aa_auto_sdr.pipeline.watch import (
    StopToken,
    WatchContext,
    run_watch_loop,
)
from aa_auto_sdr.snapshot._duration import parse_duration

logger = logging.getLogger(__name__)


# --- Real collaborators ----------------------------------------------------


class _WallClock:
    def utcnow(self) -> datetime:
        return datetime.now(UTC)


class _RealSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class _BuildSdrFetcher:
    """Adapter from build_sdr to the Fetcher protocol.

    Holds a long-lived AaClient (built once per watch invocation) and a
    tool_version string for the SdrDocument. The fetcher is what
    `run_one_cycle` calls every cycle.
    """

    client: Any  # AaClient — typed Any to avoid an import at module load
    tool_version: str

    def fetch_snapshot(self, rsid: str) -> Any:
        from aa_auto_sdr.sdr.builder import build_sdr

        return build_sdr(
            client=self.client,
            rsid=rsid,
            captured_at=datetime.now(UTC),
            tool_version=self.tool_version,
        )


@dataclass
class _SnapshotStoreAdapter:
    snapshot_dir: Path

    def latest(self, rsid: str) -> dict | None:
        from aa_auto_sdr.snapshot.store import list_snapshots, load_snapshot

        paths = list_snapshots(self.snapshot_dir, rsid=rsid)
        if not paths:
            return None
        return load_snapshot(paths[-1])

    def save(self, rsid: str, doc: Any) -> tuple[Path, dict]:  # noqa: ARG002
        """Persist the SdrDocument and return (path, envelope_dict).

        `load_snapshot(path)` is the canonical envelope-from-disk path; calling
        it immediately after save guarantees the in-memory envelope matches the
        on-disk one. One extra disk read per cycle; <1 ms for typical sizes."""
        from aa_auto_sdr.snapshot.store import load_snapshot, save_snapshot

        path = save_snapshot(doc, snapshot_dir=self.snapshot_dir)
        envelope = load_snapshot(path)
        return path, envelope


# --- Notion watch publisher ------------------------------------------------


@dataclass
class _NotionWatchPublisher:
    """Reads the snapshot envelope at `snapshot_path` and publishes it to Notion.

    Constructed only when ``--format notion`` is active. The `publish` method
    is called by `run_watch_loop` after baseline and real-change cycles.
    """

    client: Any  # notion_client.Client — typed Any to avoid heavy import at module load
    parent_page_id: str
    registry_path: Path
    database_id: str | None
    disable_registry: bool
    company: str | None

    def publish(self, *, snapshot_path: Path, rsid: str) -> None:  # noqa: ARG002
        import json

        from aa_auto_sdr.cli.commands.push_to_notion import publish_payload_to_notion

        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        publish_payload_to_notion(
            self.client,
            payload,
            parent_page_id=self.parent_page_id,
            registry_path=self.registry_path,
            force_new=False,
            database_id=self.database_id,
            disable_registry=self.disable_registry,
            company=self.company,
        )


# --- Handler ---------------------------------------------------------------


def run(ns: argparse.Namespace, *, _injected: Any = None) -> int:
    """Dispatch entry for `--watch`. Returns an int exit code.

    `_injected` is a test seam: when set, it provides fakes for fetcher /
    store / clock / sleeper / emitter / max_cycles, bypassing real I/O.
    """
    # --- 1. Validate flag combinations ------------------------------------
    if not ns.rsids:
        print("error: --watch requires at least one RSID positional", file=sys.stderr)
        return int(ExitCode.USAGE)
    if ns.interval is None:
        print("error: --watch requires --interval (e.g. --interval 1h)", file=sys.stderr)
        return int(ExitCode.USAGE)
    if getattr(ns, "watch_threshold", 1) < 0:
        print("error: --watch-threshold must be non-negative", file=sys.stderr)
        return int(ExitCode.USAGE)
    fmt = getattr(ns, "format", None)
    if fmt is not None and fmt not in ("json", "notion"):
        print(
            f"error: --format={fmt!r} is not compatible with --watch "
            f"(only `json` is allowed; watch emits NDJSON on stdout)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    if getattr(ns, "quality_policy", None) is not None:
        print(
            "error: --quality-policy is not compatible with --watch (watch is monitoring, not policy gating)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    if getattr(ns, "fail_on_quality", None) is not None:
        print(
            "error: --fail-on-quality is not compatible with --watch (watch is monitoring, not policy gating)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    # --- 2. Parse --interval ----------------------------------------------
    try:
        interval = parse_duration(ns.interval)
    except ValueError as e:
        print(f"error: invalid --interval value: {e}", file=sys.stderr)
        return int(ExitCode.USAGE)
    if interval.total_seconds() <= 0:
        # 0h would tight-loop the watch driver. parse_duration accepts it
        # (any non-negative integer with a unit), so we reject here at the
        # watch boundary where the semantic of "cadence" demands > 0.
        print(
            f"error: --interval must be greater than zero (got {ns.interval!r})",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    threshold = int(ns.watch_threshold)

    # --- 3. Build the watch context --------------------------------------
    snapshot_dir: Path | None = None
    if _injected is not None:
        fetcher = _injected.fetcher
        store = _injected.store
        clock = _injected.clock
        sleeper = _injected.sleeper
        emitter = _injected.emitter
        max_cycles = _injected.max_cycles
    else:
        fetcher = _build_real_fetcher(ns)
        snapshot_dir = resolve_snapshot_dir(ns)
        store = _SnapshotStoreAdapter(snapshot_dir=snapshot_dir)
        clock = _WallClock()
        sleeper = _RealSleeper()
        emitter = StdoutEmitter()
        max_cycles = None  # infinite by default

    # Wrap the emitter so we log a watch_cycle_complete event per emit.
    real_emitter = emitter

    class _LoggingEmitter:
        def emit(self, payload: dict) -> None:
            real_emitter.emit(payload)
            # Only emit watch_cycle_complete for `change` events — they're the
            # only ones with a meaningful change_count. Baseline and error are
            # observable via their stdout NDJSON; no need to double-log them.
            if payload.get("event") != "change":
                return
            summary = payload.get("summary") or {}
            change_count = summary.get("added", 0) + summary.get("removed", 0) + summary.get("modified", 0)
            logger.info(
                "watch_cycle_complete cycle=%d rsid=%s change_count=%d emitted=%s",
                payload.get("cycle", 0),
                payload.get("rsid", "?"),
                change_count,
                True,
                extra={
                    "cycle": payload.get("cycle", 0),
                    "rsid": payload.get("rsid", "?"),
                    "change_count": change_count,
                    "emitted": True,
                },
            )

    emitter = _LoggingEmitter()  # type: ignore[assignment]

    # --- Build optional Notion publisher (only for --format notion) ----------
    notion_publisher = None
    if fmt == "notion" and _injected is None:
        notion_publisher = _build_notion_publisher(ns, snapshot_dir=snapshot_dir)

    # Allow tests to inject a notion_publisher via _injected.
    if _injected is not None and hasattr(_injected, "notion_publisher"):
        notion_publisher = _injected.notion_publisher

    ctx = WatchContext(
        fetcher=fetcher,
        snapshot_store=store,
        clock=clock,
        sleeper=sleeper,
        emitter=emitter,
        ignore_fields=frozenset(getattr(ns, "ignore_fields", []) or []),
        extended_fields=bool(getattr(ns, "extended_fields", False)),
        git_commit=getattr(ns, "git_commit", False),
        git_push=getattr(ns, "git_push", False),
        git_message=getattr(ns, "git_message", None),
        snapshot_dir=snapshot_dir,
        notion_publisher=notion_publisher,
    )

    # --- 4. Install signal handlers --------------------------------------
    stop = StopToken()
    if _injected is None:
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())

    # --- 5. Log start + drive the loop -----------------------------------
    logger.info(
        "watch_loop_start rsids=%d interval=%s watch_threshold=%d",
        len(ns.rsids),
        ns.interval,
        threshold,
        extra={
            "rsids": len(ns.rsids),
            "interval": ns.interval,
            "watch_threshold": threshold,
        },
    )
    try:
        rc, cycles_completed = run_watch_loop(
            ctx=ctx,
            rsids=ns.rsids,
            interval=interval,
            threshold=threshold,
            stop=stop,
            max_cycles=max_cycles,
        )
        reason = "max_cycles" if (max_cycles is not None and cycles_completed >= max_cycles) else "sigint"
        logger.info(
            "watch_loop_stop reason=%s cycles_completed=%d",
            reason,
            cycles_completed,
            extra={"reason": reason, "cycles_completed": cycles_completed},
        )
        return int(rc)
    except Exception:
        logger.exception(
            "watch_loop_stop reason=%s cycles_completed=%d",
            "fatal",
            -1,
            extra={"reason": "fatal", "cycles_completed": -1},
        )
        return int(ExitCode.GENERIC)


# --- helpers -------------------------------------------------------------


def _build_real_fetcher(ns: argparse.Namespace) -> _BuildSdrFetcher:
    """Resolve credentials → build AaClient → wrap in fetcher adapter.

    Mirrors the credential + client construction in cli/commands/generate.py.
    Lazy imports keep fast-path help free of heavy deps.
    """
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.core import credentials, version

    profile = getattr(ns, "profile", None)
    creds = credentials.resolve(profile=profile)
    client = AaClient.from_credentials(creds)
    return _BuildSdrFetcher(client=client, tool_version=version.__version__)


def _build_notion_publisher(
    ns: argparse.Namespace,
    *,
    snapshot_dir: Path | None,
) -> _NotionWatchPublisher:
    """Build a real _NotionWatchPublisher from the namespace.

    Lazy imports keep this off the fast path.
    """
    from aa_auto_sdr.output.notion_client_guard import (
        _require_notion_client,
        resolve_notion_company,
        resolve_notion_credentials,
        resolve_notion_database_id,
    )
    from aa_auto_sdr.output.notion_registry import get_registry_path

    Client = _require_notion_client()
    token, parent_page_id = resolve_notion_credentials()
    client = Client(auth=token)

    # Use --output-dir if supplied; fall back to CWD.
    output_dir_raw = getattr(ns, "output_dir", None)
    if output_dir_raw:
        effective_dir = Path(output_dir_raw)
    elif snapshot_dir is not None:
        effective_dir = snapshot_dir
    else:
        effective_dir = Path.cwd()
    registry_path = get_registry_path(effective_dir)

    database_id = resolve_notion_database_id(
        cli_override=getattr(ns, "notion_registry_database", None),
        disabled=bool(getattr(ns, "no_notion_registry", False)),
    )
    company = resolve_notion_company(
        cli_override=getattr(ns, "notion_company", None),
        aa_company_id=None,
    )

    return _NotionWatchPublisher(
        client=client,
        parent_page_id=parent_page_id,
        registry_path=registry_path,
        database_id=database_id,
        disable_registry=bool(getattr(ns, "no_notion_registry", False)),
        company=company,
    )
