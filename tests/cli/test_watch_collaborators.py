"""Unit coverage for the real-collaborator adapters and builder helpers in
``cli/commands/watch.py``.

The end-to-end dispatch path is exercised in ``test_watch_command.py`` via the
``_injected`` seam. This module covers the pieces that seam *bypasses*: the
``_WallClock`` / ``_RealSleeper`` / ``_BuildSdrFetcher`` / ``_SnapshotStoreAdapter``
/ ``_NotionWatchPublisher`` adapters, the ``_build_real_fetcher`` /
``_build_notion_publisher`` constructors, the signal-handler install in the
non-injected branch, and the fatal-exception guard around ``run_watch_loop``.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aa_auto_sdr.cli.commands import watch as watch_mod
from aa_auto_sdr.core.exit_codes import ExitCode


class _NoopNotionClient:
    """Minimal Notion client stand-in for _build_notion_publisher fallback tests."""

    def __init__(self, *, auth):
        self.auth = auth


# --- adapters --------------------------------------------------------------


def test_wallclock_returns_aware_utc_datetime() -> None:
    now = watch_mod._WallClock().utcnow()
    assert isinstance(now, datetime)
    assert now.tzinfo is UTC


def test_real_sleeper_invokes_time_sleep(monkeypatch) -> None:
    calls: list[float] = []
    monkeypatch.setattr(watch_mod.time, "sleep", calls.append)
    watch_mod._RealSleeper().sleep(2.5)
    assert calls == [2.5]


def test_build_sdr_fetcher_delegates_to_build_sdr(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_build_sdr(*, client, rsid, captured_at, tool_version):
        captured.update(client=client, rsid=rsid, tool_version=tool_version)
        return {"rsid": rsid}

    monkeypatch.setattr("aa_auto_sdr.sdr.builder.build_sdr", _fake_build_sdr)
    fetcher = watch_mod._BuildSdrFetcher(client="CLIENT", tool_version="9.9.9")
    out = fetcher.fetch_snapshot("rs_a")
    assert out == {"rsid": "rs_a"}
    assert captured == {"client": "CLIENT", "rsid": "rs_a", "tool_version": "9.9.9"}


def test_snapshot_store_adapter_latest_returns_none_when_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("aa_auto_sdr.snapshot.store.list_snapshots", lambda *_a, **_k: [])
    adapter = watch_mod._SnapshotStoreAdapter(snapshot_dir=tmp_path)
    assert adapter.latest("rs_a") is None


def test_snapshot_store_adapter_latest_loads_last_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "aa_auto_sdr.snapshot.store.list_snapshots",
        lambda *_a, **_k: [tmp_path / "1.json", tmp_path / "2.json"],
    )
    loaded: list[Path] = []

    def _fake_load(path):
        loaded.append(path)
        return {"loaded": str(path)}

    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", _fake_load)
    adapter = watch_mod._SnapshotStoreAdapter(snapshot_dir=tmp_path)
    out = adapter.latest("rs_a")
    # latest() loads paths[-1].
    assert out == {"loaded": str(tmp_path / "2.json")}
    assert loaded == [tmp_path / "2.json"]


def test_snapshot_store_adapter_save_persists_then_reloads(monkeypatch, tmp_path: Path) -> None:
    saved_path = tmp_path / "rs_a" / "snap.json"

    def _fake_save(doc, *, snapshot_dir):
        assert snapshot_dir == tmp_path
        return saved_path

    monkeypatch.setattr("aa_auto_sdr.snapshot.store.save_snapshot", _fake_save)
    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", lambda p: {"reloaded": str(p)})
    adapter = watch_mod._SnapshotStoreAdapter(snapshot_dir=tmp_path)
    path, envelope = adapter.save("rs_a", {"doc": True})
    assert path == saved_path
    assert envelope == {"reloaded": str(saved_path)}


def test_notion_watch_publisher_reads_envelope_and_publishes(monkeypatch, tmp_path: Path) -> None:
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"rsid": "rs_a"}), encoding="utf-8")
    calls: list[dict] = []

    def _fake_publish(client, payload, **kwargs):
        calls.append({"client": client, "payload": payload, **kwargs})

    monkeypatch.setattr(
        "aa_auto_sdr.cli.commands.push_to_notion.publish_payload_to_notion",
        _fake_publish,
    )
    pub = watch_mod._NotionWatchPublisher(
        client="NOTION",
        parent_page_id="parent-1",
        registry_path=tmp_path / ".notion_pages.json",
        database_id="db-1",
        disable_registry=False,
        company="Acme",
    )
    pub.publish(snapshot_path=snap, rsid="rs_a")
    assert len(calls) == 1
    call = calls[0]
    assert call["client"] == "NOTION"
    assert call["payload"] == {"rsid": "rs_a"}
    assert call["parent_page_id"] == "parent-1"
    assert call["database_id"] == "db-1"
    assert call["force_new"] is False
    assert call["company"] == "Acme"


# --- builder helpers -------------------------------------------------------


def test_build_real_fetcher_resolves_creds_and_client(monkeypatch) -> None:
    monkeypatch.setattr("aa_auto_sdr.core.credentials.resolve", lambda *, profile: {"creds": profile})
    monkeypatch.setattr(
        "aa_auto_sdr.api.client.AaClient.from_credentials",
        classmethod(lambda _cls, creds: f"client:{creds}"),
    )
    ns = argparse.Namespace(profile="prod")
    fetcher = watch_mod._build_real_fetcher(ns)
    assert isinstance(fetcher, watch_mod._BuildSdrFetcher)
    assert fetcher.client == "client:{'creds': 'prod'}"
    assert fetcher.tool_version  # version string is non-empty


def test_build_notion_publisher_wires_resolvers(monkeypatch, tmp_path: Path) -> None:
    class _FakeClient:
        def __init__(self, *, auth):
            self.auth = auth

    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard._require_notion_client",
        lambda: _FakeClient,
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_credentials",
        lambda: ("tok", "parent-99"),
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_database_id",
        lambda **_k: "db-99",
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_company",
        lambda **_k: "Globex",
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_registry.get_registry_path",
        lambda d: Path(d) / ".notion_pages.json",
    )
    ns = argparse.Namespace(
        output_dir=str(tmp_path),
        notion_registry_database=None,
        no_notion_registry=False,
        notion_company=None,
    )
    pub = watch_mod._build_notion_publisher(ns, snapshot_dir=None)
    assert isinstance(pub, watch_mod._NotionWatchPublisher)
    assert isinstance(pub.client, _FakeClient)
    assert pub.client.auth == "tok"
    assert pub.parent_page_id == "parent-99"
    assert pub.database_id == "db-99"
    assert pub.company == "Globex"
    assert pub.registry_path == tmp_path / ".notion_pages.json"


def test_build_notion_publisher_falls_back_to_cwd(monkeypatch) -> None:
    """No --output-dir and no snapshot_dir → registry path rooted at the CWD."""
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard._require_notion_client",
        lambda: _NoopNotionClient,
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_credentials",
        lambda: ("tok", "parent"),
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_database_id",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_company",
        lambda **_k: None,
    )
    captured: list[Path] = []
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_registry.get_registry_path",
        lambda d: captured.append(d) or (Path(d) / ".notion_pages.json"),
    )
    ns = argparse.Namespace(
        output_dir=None,
        notion_registry_database=None,
        no_notion_registry=False,
        notion_company=None,
    )
    watch_mod._build_notion_publisher(ns, snapshot_dir=None)
    assert captured == [Path.cwd()]


def test_build_notion_publisher_falls_back_to_snapshot_dir(monkeypatch, tmp_path: Path) -> None:
    """No --output-dir but a snapshot_dir → registry path rooted at snapshot_dir."""
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard._require_notion_client",
        lambda: _NoopNotionClient,
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_credentials",
        lambda: ("tok", "parent"),
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_database_id",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_client_guard.resolve_notion_company",
        lambda **_k: None,
    )
    captured: list[Path] = []
    monkeypatch.setattr(
        "aa_auto_sdr.output.notion_registry.get_registry_path",
        lambda d: captured.append(d) or (Path(d) / ".notion_pages.json"),
    )
    ns = argparse.Namespace(
        output_dir=None,
        notion_registry_database=None,
        no_notion_registry=True,
        notion_company=None,
    )
    pub = watch_mod._build_notion_publisher(ns, snapshot_dir=tmp_path)
    assert captured == [tmp_path]
    assert pub.disable_registry is True


# --- run() non-injected and fatal-path branches ----------------------------


def _ns(**overrides) -> argparse.Namespace:
    defaults = {
        "rsids": ["rs_a"],
        "watch": True,
        "interval": "1h",
        "watch_threshold": 1,
        "ignore_fields": [],
        "extended_fields": False,
        "format": None,
        "quality_policy": None,
        "fail_on_quality": None,
        "profile": None,
        "snapshot_dir": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_run_real_branch_installs_signal_handlers(monkeypatch, tmp_path: Path) -> None:
    """With no injection, run() builds real collaborators and installs SIGINT/SIGTERM."""
    monkeypatch.setattr(watch_mod, "_build_real_fetcher", lambda _ns: object())
    monkeypatch.setattr(watch_mod, "resolve_snapshot_dir", lambda _ns: tmp_path)
    monkeypatch.setattr(watch_mod, "run_watch_loop", lambda **_kw: (int(ExitCode.OK), 1))

    installed: list[Any] = []
    monkeypatch.setattr(watch_mod.signal, "signal", lambda sig, _handler: installed.append(sig))

    rc = watch_mod.run(_ns())
    assert rc == int(ExitCode.OK)
    assert watch_mod.signal.SIGINT in installed
    assert watch_mod.signal.SIGTERM in installed


def test_run_real_branch_notion_format_builds_publisher(monkeypatch, tmp_path: Path) -> None:
    """format='notion' in the non-injected branch builds a real Notion publisher."""
    monkeypatch.setattr(watch_mod, "_build_real_fetcher", lambda _ns: object())
    monkeypatch.setattr(watch_mod, "resolve_snapshot_dir", lambda _ns: tmp_path)
    monkeypatch.setattr(watch_mod.signal, "signal", lambda _sig, _handler: None)

    built: list[Any] = []
    sentinel = object()
    monkeypatch.setattr(
        watch_mod,
        "_build_notion_publisher",
        lambda _ns, *, snapshot_dir: built.append(snapshot_dir) or sentinel,
    )

    captured: dict[str, Any] = {}

    def _spy_loop(*, ctx, rsids, interval, threshold, stop, max_cycles):
        captured["notion_publisher"] = ctx.notion_publisher
        return int(ExitCode.OK), 1

    monkeypatch.setattr(watch_mod, "run_watch_loop", _spy_loop)

    rc = watch_mod.run(_ns(format="notion"))
    assert rc == int(ExitCode.OK)
    assert built == [tmp_path]
    assert captured["notion_publisher"] is sentinel


def test_run_fatal_exception_returns_generic(monkeypatch) -> None:
    """A crash inside run_watch_loop is caught, logged, and mapped to GENERIC."""

    def _boom(**kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(watch_mod, "run_watch_loop", _boom)

    class _Inj:
        fetcher = object()
        store = object()
        clock = object()
        sleeper = object()
        emitter = type("E", (), {"emit": lambda _self, _p: None})()
        max_cycles = 1

    rc = watch_mod.run(_ns(), _injected=_Inj())
    assert rc == int(ExitCode.GENERIC)


def test_run_uses_injected_notion_publisher(monkeypatch) -> None:
    """An _injected carrying a notion_publisher threads it into the WatchContext."""
    captured: dict[str, Any] = {}

    def _spy_loop(*, ctx, rsids, interval, threshold, stop, max_cycles):
        captured["notion_publisher"] = ctx.notion_publisher
        return int(ExitCode.OK), 1

    monkeypatch.setattr(watch_mod, "run_watch_loop", _spy_loop)

    sentinel = object()

    class _Inj:
        fetcher = object()
        store = object()
        clock = object()
        sleeper = object()
        emitter = type("E", (), {"emit": lambda _self, _p: None})()
        max_cycles = 1
        notion_publisher = sentinel

    rc = watch_mod.run(_ns(), _injected=_Inj())
    assert rc == int(ExitCode.OK)
    assert captured["notion_publisher"] is sentinel
