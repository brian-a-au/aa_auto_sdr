"""End-to-end --watch dispatch with fakes for fetch/store/sleep/signal."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aa_auto_sdr.cli.commands.watch import run as watch_run
from aa_auto_sdr.core.exit_codes import ExitCode


@dataclass
class _FakeFetcher:
    rsid_to_doc: dict[str, Any] = field(default_factory=dict)
    raise_for: dict[str, BaseException] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def fetch_snapshot(self, rsid: str) -> Any:
        self.calls.append(rsid)
        if rsid in self.raise_for:
            raise self.raise_for[rsid]
        return self.rsid_to_doc.get(rsid, {"rsid": rsid})


@dataclass
class _FakeStore:
    latest_by_rsid: dict[str, dict | None] = field(default_factory=dict)
    saved: list[tuple[str, Any]] = field(default_factory=list)

    def latest(self, rsid: str) -> dict | None:
        return self.latest_by_rsid.get(rsid)

    def save(self, rsid: str, doc: Any) -> tuple[Path, dict]:
        self.saved.append((rsid, doc))
        path = Path(f"/tmp/{rsid}/{len(self.saved)}.json")
        # Return a minimal compare-compatible envelope.
        envelope = {
            "rsid": rsid,
            "captured_at": f"2026-05-10T14:00:0{len(self.saved)}Z",
            "tool_version": "1.14.0",
            "components": {
                "report_suite": {"rsid": rsid, "name": rsid},
                "dimensions": [],
                "metrics": [],
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
            },
        }
        self.latest_by_rsid[rsid] = envelope
        return path, envelope


@dataclass
class _FakeClock:
    _now: datetime = field(default_factory=lambda: datetime(2026, 5, 10, tzinfo=UTC))

    def utcnow(self) -> datetime:
        out = self._now
        self._now = out + timedelta(seconds=1)
        return out


@dataclass
class _FakeSleeper:
    calls: list[float] = field(default_factory=list)

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


@dataclass
class _FakeEmitter:
    events: list[dict] = field(default_factory=list)

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


@dataclass
class _Injection:
    fetcher: _FakeFetcher = field(default_factory=_FakeFetcher)
    store: _FakeStore = field(default_factory=_FakeStore)
    clock: _FakeClock = field(default_factory=_FakeClock)
    sleeper: _FakeSleeper = field(default_factory=_FakeSleeper)
    emitter: _FakeEmitter = field(default_factory=_FakeEmitter)
    max_cycles: int | None = 1


def _make_inj() -> _Injection:
    return _Injection()


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


class TestUsageValidation:
    def test_watch_without_interval_returns_usage(self, capsys) -> None:
        ns = _ns(interval=None)
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE
        err = capsys.readouterr().err
        assert "--interval" in err

    def test_watch_with_invalid_interval_unit_returns_usage(self) -> None:
        ns = _ns(interval="15m")  # minutes unsupported
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE

    def test_watch_with_no_rsids_returns_usage(self) -> None:
        ns = _ns(rsids=[])
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE

    def test_watch_with_negative_threshold_returns_usage(self) -> None:
        ns = _ns(watch_threshold=-1)
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE

    def test_watch_with_format_returns_usage(self, capsys) -> None:
        ns = _ns(format="excel")
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE
        assert "--format" in capsys.readouterr().err

    def test_watch_with_quality_policy_returns_usage(self, capsys) -> None:
        ns = _ns(quality_policy="strict")
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE
        assert "--quality-policy" in capsys.readouterr().err

    def test_watch_with_fail_on_quality_returns_usage(self, capsys) -> None:
        ns = _ns(fail_on_quality="error")
        rc = watch_run(ns, _injected=_make_inj())
        assert rc == ExitCode.USAGE
        assert "--fail-on-quality" in capsys.readouterr().err


class TestDispatchIntegration:
    def test_two_rsids_three_cycles_baseline_then_diff(self) -> None:
        inj = _make_inj()
        inj.max_cycles = 3
        ns = _ns(rsids=["rs_a", "rs_b"], interval="1h", watch_threshold=0)
        rc = watch_run(ns, _injected=inj)
        assert rc == ExitCode.OK
        # 2 rsids × 3 cycles = 6 events when threshold=0.
        assert len(inj.emitter.events) == 6
        assert inj.emitter.events[0]["event"] == "baseline"
        assert inj.emitter.events[1]["event"] == "baseline"
        for ev in inj.emitter.events[2:]:
            assert ev["event"] == "change"

    def test_fetch_error_continues_loop(self) -> None:
        inj = _make_inj()
        inj.fetcher.raise_for["rs_a"] = RuntimeError("503")
        inj.max_cycles = 2
        ns = _ns(rsids=["rs_a", "rs_b"], interval="1h", watch_threshold=0)
        rc = watch_run(ns, _injected=inj)
        assert rc == ExitCode.OK
        kinds = [e["event"] for e in inj.emitter.events]
        assert kinds.count("error") == 2
        assert "baseline" in kinds
        assert "change" in kinds
