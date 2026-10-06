"""Real watch dispatch/client/builder/loop with only external boundaries mocked.

Removing watch's policy forwarding must break the nondefault attempt counts,
backoff schedules and recovery cases. No Adobe, Notion or Git operations run.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from itertools import count
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from aa_auto_sdr.cli.commands import watch
from aa_auto_sdr.cli.main import run
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import ApiError, AuthError
from aa_auto_sdr.pipeline.watch import run_watch_loop
from aa_auto_sdr.snapshot.git import GitOpResult
from aa_auto_sdr.snapshot.store import list_snapshots, load_snapshot


@pytest.fixture
def sdk(monkeypatch, tmp_path):
    """Keep policy resolution, client construction and the bounded loop real."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(socket.socket, "connect", MagicMock(side_effect=AssertionError("network forbidden")))
    handle = MagicMock()
    login = MagicMock()
    login.getCompanyId.return_value = [{"globalCompanyId": "offline"}]
    handle.getReportSuites.side_effect = lambda **kw: [{"rsid": kw["rsid_list"], "name": "Offline"}]
    for method in (
        "getMetrics",
        "getDimensions",
        "getSegments",
        "getCalculatedMetrics",
        "getVirtualReportSuites",
        "getClassificationDatasets",
    ):
        getattr(handle, method).return_value = []
    monkeypatch.setattr("aa_auto_sdr.api.client.aanalytics2.configure", MagicMock())
    monkeypatch.setattr("aa_auto_sdr.api.client.aanalytics2.Login", lambda: login)
    monkeypatch.setattr("aa_auto_sdr.api.client.aanalytics2.Analytics", lambda _: handle)
    creds = Credentials("offline", "offline", "offline", "offline", "test")
    monkeypatch.setattr("aa_auto_sdr.core.credentials.resolve", lambda **_: creds)
    state = SimpleNamespace(handle=handle, login=login, sleeps=[], cycles=1, contexts=[], root=tmp_path / "snapshots")
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", state.sleeps.append)
    monkeypatch.setattr("aa_auto_sdr.api.resilience.random.uniform", lambda *_: 0)
    monkeypatch.setattr(watch.signal, "signal", lambda *_: None)
    ticks = count()
    monkeypatch.setattr(
        watch._WallClock, "utcnow", lambda _: datetime(2026, 10, 6, tzinfo=UTC) + timedelta(hours=next(ticks))
    )
    monkeypatch.setattr(watch._RealSleeper, "sleep", lambda *_: None)

    def bounded_loop(**kwargs):
        state.contexts.append(kwargs["ctx"])
        return run_watch_loop(**{**kwargs, "max_cycles": state.cycles})

    monkeypatch.setattr(watch, "run_watch_loop", bounded_loop)
    state.git = MagicMock(return_value=GitOpResult(ok=True, committed=True, commit_sha="offline", pushed=False))
    state.publisher = MagicMock()
    monkeypatch.setattr("aa_auto_sdr.pipeline.watch.git_commit_snapshot", state.git)
    monkeypatch.setattr(watch, "_build_notion_publisher", lambda *_a, **_kw: state.publisher)
    yield state
    # Mirror existing CLI smoke tests: run() replaces the root handlers.
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)
        handler.close()


def invoke(sdk, flags=(), rsids=("demo",)):
    return run([*rsids, "--watch", "--interval", "1h", "--snapshot-dir", str(sdk.root), *flags])


def events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


@pytest.mark.parametrize("stage", ["bootstrap", "metrics"])
@pytest.mark.parametrize(
    "error", [KeyError("stub"), ValueError("stub"), requests.Timeout("offline"), requests.ConnectionError("offline")]
)
@pytest.mark.parametrize(
    ("flags", "attempts", "delays"),
    [
        ([], 4, [0.5, 1, 2]),
        (["--max-retries", "0"], 1, []),
        (["--max-retries", "2", "--retry-base-delay", "2", "--retry-max-delay", "3"], 3, [2, 3]),
        (["--agent-mode", "--max-retries", "6"], 7, [0.5, 1, 2, 4, 8, 10]),
    ],
)
def test_watch_honors_retry_exhaustion(sdk, capsys, stage, error, flags, attempts, delays):
    target = sdk.login.getCompanyId if stage == "bootstrap" else sdk.handle.getMetrics
    target.side_effect = error
    if stage == "bootstrap":
        with pytest.raises((ApiError, requests.Timeout, requests.ConnectionError)):
            invoke(sdk, flags)
        assert events(capsys) == []
        assert sdk.contexts == []  # startup failure never starts the watcher
    else:
        assert invoke(sdk, flags) == 0
        payloads = events(capsys)
        assert [p["event"] for p in payloads] == ["error"]
        assert payloads[0]["error_type"] in ("TransientApiError", "ApiError")
    assert target.call_count == attempts
    assert sdk.sleeps == delays
    assert list_snapshots(sdk.root, rsid="demo") == []
    sdk.git.assert_not_called()
    sdk.publisher.publish.assert_not_called()


@pytest.mark.parametrize("stage", ["bootstrap", "metrics"])
@pytest.mark.parametrize("failures", [0, 4])
def test_watch_high_budget_recovers_before_exhaustion(sdk, capsys, stage, failures):
    target = sdk.login.getCompanyId if stage == "bootstrap" else sdk.handle.getMetrics
    good = [{"globalCompanyId": "offline"}] if stage == "bootstrap" else []
    target.side_effect = [KeyError("stub")] * failures + [good]
    flags = ["--agent-mode", "--max-retries", "6", "--retry-base-delay", "2", "--retry-max-delay", "3"]
    assert invoke(sdk, flags) == 0
    assert [p["event"] for p in events(capsys)] == ["baseline"]
    assert target.call_count == failures + 1
    assert sdk.sleeps == ([] if failures == 0 else [2, 3, 3, 3])
    assert asdict(sdk.contexts[0].fetcher.client.retry_policy) == {"max_retries": 6, "base_delay": 2, "max_delay": 3}
    assert len(list_snapshots(sdk.root, rsid="demo")) == 1


@pytest.mark.parametrize("stage", ["bootstrap", "metrics"])
@pytest.mark.parametrize(
    "error", [AuthError("offline"), AttributeError("bad SDK shape"), KeyError("['dataGroup'] not in index")]
)
def test_watch_permanent_failure_bypasses_retries(sdk, capsys, stage, error):
    target = sdk.login.getCompanyId if stage == "bootstrap" else sdk.handle.getMetrics
    target.side_effect = error
    if stage == "bootstrap":
        with pytest.raises((AuthError, AttributeError, ApiError)):
            invoke(sdk, ["--max-retries", "6"])
        assert events(capsys) == []
    else:
        assert invoke(sdk, ["--max-retries", "6"]) == 0
        assert [p["event"] for p in events(capsys)] == ["error"]
    assert target.call_count == 1
    assert sdk.sleeps == []
    assert list_snapshots(sdk.root, rsid="demo") == []


@pytest.mark.parametrize("stage", ["bootstrap", "metrics"])
@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(9)])
def test_watch_control_flow_stops_without_retry(sdk, capsys, stage, error):
    target = sdk.login.getCompanyId if stage == "bootstrap" else sdk.handle.getMetrics
    target.side_effect = error
    with pytest.raises(type(error)):
        invoke(sdk, ["--max-retries", "6"])
    assert events(capsys) == []
    assert target.call_count == 1
    assert sdk.sleeps == []
    assert list_snapshots(sdk.root, rsid="demo") == []


def test_watch_helper_missing_policy_keeps_client_defaults(sdk):
    fetcher = watch._build_real_fetcher(argparse.Namespace(profile=None))
    assert asdict(fetcher.client.retry_policy) == {"max_retries": 3, "base_delay": 0.5, "max_delay": 10}


@pytest.mark.parametrize("prior", [False, True])
def test_watch_failed_cycle_keeps_baseline_for_next_success(sdk, capsys, prior):
    flags = ["--max-retries", "0", "--format", "notion", "--git-commit"]
    sdk.handle.getMetrics.return_value = [{"id": "metric", "name": "Before"}]
    if prior:
        assert invoke(sdk, flags) == 0
        assert [p["event"] for p in events(capsys)] == ["baseline"]
    sdk.git.reset_mock()
    sdk.publisher.reset_mock()
    previous = list_snapshots(sdk.root, rsid="demo")
    sdk.cycles = 2
    attempts = count()

    def fail_then_recover(**_kwargs):
        if next(attempts) == 0:
            raise requests.Timeout("Bearer abc123def456ghi789")
        # The next cycle sees no snapshot or success side effect from failure.
        assert list_snapshots(sdk.root, rsid="demo") == previous
        sdk.git.assert_not_called()
        sdk.publisher.publish.assert_not_called()
        return [{"id": "metric", "name": "After"}]

    sdk.handle.getMetrics.side_effect = fail_then_recover
    assert invoke(sdk, flags) == 0
    recovery = events(capsys)
    assert [p["event"] for p in recovery] == ["error", "change" if prior else "baseline"]
    assert "abc123def456ghi789" not in recovery[0]["error"]
    assert "snapshot_path" not in recovery[0]
    if prior:
        assert recovery[1]["summary"]["modified"] == 1
    assert len(list_snapshots(sdk.root, rsid="demo")) == len(previous) + 1
    sdk.git.assert_called_once()
    sdk.publisher.publish.assert_called_once()


def test_watch_failed_rsid_continues_to_next_and_next_cycle(sdk, capsys):
    sdk.cycles = 2
    sdk.handle.getMetrics.side_effect = [requests.Timeout("offline"), [], [], []]
    assert invoke(sdk, ["--max-retries", "0"], rsids=("first", "second")) == 0
    assert [(p["rsid"], p["event"]) for p in events(capsys)] == [
        ("first", "error"),
        ("second", "baseline"),
        ("first", "baseline"),
    ]
    assert sdk.handle.getMetrics.call_count == 4
    assert sdk.sleeps == []
    assert len(list_snapshots(sdk.root, rsid="first")) == 1
    assert len(list_snapshots(sdk.root, rsid="second")) == 2


@pytest.mark.parametrize(
    ("method", "component", "error", "attempts"),
    [
        ("getVirtualReportSuites", "virtual_report_suites", KeyError("content"), 1),
        ("getVirtualReportSuites", "virtual_report_suites", requests.Timeout("offline"), 3),
        ("getClassificationDatasets", "classifications", requests.ConnectionError("offline"), 3),
    ],
)
def test_watch_optional_fetch_failure_retains_degradation(sdk, capsys, method, component, error, attempts):
    target = getattr(sdk.handle, method)
    target.side_effect = error
    assert invoke(sdk, ["--max-retries", "2", "--retry-base-delay", "2", "--retry-max-delay", "3"]) == 0
    assert [p["event"] for p in events(capsys)] == ["baseline"]
    assert target.call_count == attempts
    assert sdk.sleeps == ([] if attempts == 1 else [2, 3])
    envelope = load_snapshot(list_snapshots(sdk.root, rsid="demo")[0])
    assert envelope["schema"] == "aa-sdr-snapshot/v4"
    assert envelope["degraded_components"] == [component]
    assert envelope["partial_components"] == {}
