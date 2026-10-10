"""Invocation-scoped VRS enumeration contract."""

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from aa_auto_sdr.api import vrs_source
from aa_auto_sdr.api.fetch import fetch_virtual_report_suites
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.api.vrs_source import VrsSource


def _waiter_ready_event(monkeypatch: pytest.MonkeyPatch, count: int) -> Event:
    """Signal when `count` consumers have joined the source's in-flight Future."""
    ready = Event()
    lock = Lock()
    joined = 0

    class CountingFuture(Future):
        def result(self, timeout=None):
            nonlocal joined
            with lock:
                joined += 1
                if joined == count:
                    ready.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(vrs_source, "Future", CountingFuture)
    return ready


def test_fifty_consumers_share_one_enumeration(monkeypatch: pytest.MonkeyPatch):
    lock = Lock()
    entered = Event()
    release = Event()
    waiters_ready = _waiter_ready_event(monkeypatch, 15)
    calls = 0

    def enumerate_vrs(**kwargs):
        nonlocal calls
        with lock:
            calls += 1
        entered.set()
        assert release.wait(5)
        return [{"id": f"vrs-{i}", "name": f"VRS {i}", "parentRsid": f"rs-{i}"} for i in range(50)]

    client = SimpleNamespace(
        handle=SimpleNamespace(getVirtualReportSuites=enumerate_vrs),
        company_id="company-a",
        retry_policy=RetryPolicy(max_retries=0),
    )
    source = VrsSource(client)
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(fetch_virtual_report_suites, client, f"rs-{i}", source=source) for i in range(50)]
        assert entered.wait(5)
        assert waiters_ready.wait(5)
        release.set()
        outcomes = [future.result(timeout=5) for future in futures]
    assert calls == 1
    assert [outcome.data[0].id for outcome in outcomes] == [f"vrs-{i}" for i in range(50)]
    assert all(outcome.status == "healthy" for outcome in outcomes)


def _client(enumerate_vrs, company="company-a"):
    return SimpleNamespace(
        handle=SimpleNamespace(getVirtualReportSuites=enumerate_vrs),
        company_id=company,
        retry_policy=RetryPolicy(max_retries=0),
    )


def test_empty_success_is_healthy_and_cached():
    calls = 0

    def enumerate_vrs(**kwargs):
        nonlocal calls
        calls += 1
        return []

    client = _client(enumerate_vrs)
    source = VrsSource(client)
    for rsid in ("a", "b"):
        result = fetch_virtual_report_suites(client, rsid, source=source)
        assert result.status == "healthy"
        assert result.data == []
    assert calls == 1
    fetch_virtual_report_suites(client, "a")
    fetch_virtual_report_suites(client, "b")
    assert calls == 3


def test_failed_flight_releases_waiters_and_later_success_is_retained(monkeypatch: pytest.MonkeyPatch):
    entered = Event()
    release = Event()
    waiters_ready = _waiter_ready_event(monkeypatch, 8)
    lock = Lock()
    calls = 0

    def enumerate_vrs(**kwargs):
        nonlocal calls
        with lock:
            calls += 1
            attempt = calls
        if attempt == 1:
            entered.set()
            assert release.wait(5)
            raise RuntimeError("endpoint failed")
        return [{"id": "vrs", "parentRsid": "a"}]

    client = _client(enumerate_vrs)
    source = VrsSource(client)
    with ThreadPoolExecutor(max_workers=9) as pool:
        first = pool.submit(fetch_virtual_report_suites, client, "a", source=source)
        assert entered.wait(5)
        waiting = [pool.submit(fetch_virtual_report_suites, client, "a", source=source) for _ in range(8)]
        assert waiters_ready.wait(5)
        release.set()
        results = [future.result(timeout=5) for future in [first, *waiting]]
    assert calls == 1
    assert all(result.status == "degraded" for result in results)
    assert all(result.expansion_level is None for result in results)
    assert fetch_virtual_report_suites(client, "a", source=source).data[0].id == "vrs"
    assert fetch_virtual_report_suites(client, "a", source=source).status == "healthy"
    assert calls == 2


def test_source_is_bound_to_exact_client_and_company():
    calls = 0

    def enumerate_vrs(**kwargs):
        nonlocal calls
        calls += 1
        return []

    first = _client(enumerate_vrs)
    second = _client(enumerate_vrs)
    source = VrsSource(first)
    fetch_virtual_report_suites(first, "a", source=source)
    with pytest.raises(ValueError, match="different client"):
        fetch_virtual_report_suites(second, "a", source=source)
    first.company_id = "company-b"
    with pytest.raises(ValueError, match="different client"):
        fetch_virtual_report_suites(first, "a", source=source)
    fetch_virtual_report_suites(second, "a", source=VrsSource(second))
    assert calls == 2


def test_shared_rows_do_not_leak_mutations_between_consumers():
    client = _client(lambda **_: [{"id": "vrs", "parentRsid": "a", "segmentList": ["one"]}])
    source = VrsSource(client)
    first = fetch_virtual_report_suites(client, "a", source=source)
    first.data[0].segment_list.append("changed")
    second = fetch_virtual_report_suites(client, "a", source=source)
    assert second.data[0].segment_list == ["one"]
