"""A listing page after the first that comes back as an error is retried, not dropped.

Above 1,000 report suites or virtual report suites, the SDK fetches pages 1..n
in threads and silently drops any page whose body is an error. These tests run
the real SDK listing methods offline against a fake read-only connector, so a
dropped page shows up exactly as it would against Adobe.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import aanalytics2
import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import (
    _PAGED_LISTING_PATHS,
    AaClient,
    _ListingPageGuard,
    install_listing_page_guard,
)
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.api.vrs_source import VrsSource
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import ApiError

_RS_PATH = "/collections/suites"
_VRS_PATH = "/reportsuites/virtualreportsuites"
_MAX_RETRIES = 2
_TOTAL_PAGES = 3

_ERROR_BODIES = [
    pytest.param({"error_code": "429050", "message": "Too many requests"}, id="error_code"),
    pytest.param({"error": "Request Error"}, id="error"),
    pytest.param({"errorCode": "invalid_request", "message": "bad"}, id="errorCode"),
]


class FakeConnector:
    """Serves a three-page listing. `bad_page` answers `bad_body` for its first `fail_times` calls."""

    def __init__(self, *, bad_page: int | None = None, bad_body: Any = None, fail_times: int = 0) -> None:
        self.bad_page = bad_page
        self.bad_body = bad_body
        self.fail_left = fail_times
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def getData(self, endpoint, params=None, data=None, headers=None, *args, **kwargs):
        params = dict(params or {})
        self.calls.append((endpoint, params))
        page = int(params.get("page", 0))
        if page == self.bad_page and self.fail_left > 0:
            self.fail_left -= 1
            return dict(self.bad_body) if isinstance(self.bad_body, dict) else self.bad_body
        if endpoint.endswith(_VRS_PATH):
            row = {"id": f"vrs{page}", "name": f"Virtual {page}", "parentRsid": "parent"}
        else:
            row = {"rsid": f"rs{page}", "name": f"Suite {page}", "parentRsid": "parent"}
        return {"content": [row], "totalPages": _TOTAL_PAGES, "lastPage": page == _TOTAL_PAGES - 1}

    def page0_calls(self, suffix: str) -> int:
        return sum(
            1 for endpoint, params in self.calls if endpoint.endswith(suffix) and int(params.get("page", 0)) == 0
        )


def _handle(connector: Any, *, guarded: bool = True) -> Any:
    handle = object.__new__(aanalytics2.Analytics)
    handle.loggingEnabled = False
    handle.endpoint_company = "https://example.invalid"
    handle.header = {}
    handle.connector = connector
    if guarded:
        install_listing_page_guard(handle)
    return handle


def _client(connector: Any, *, guarded: bool = True) -> AaClient:
    return AaClient(
        handle=_handle(connector, guarded=guarded),
        company_id="c",
        retry_policy=RetryPolicy(max_retries=_MAX_RETRIES, base_delay=0.001, max_delay=0.001),
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)


# --- a page that fails once recovers to the full row set -------------------------------------


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_report_suite_listing_recovers_after_one_bad_page(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=1)
    rows = fetch.fetch_report_suites_raw(_client(conn))
    assert sorted(r["rsid"] for r in rows) == ["rs0", "rs1", "rs2"]
    assert conn.page0_calls(_RS_PATH) == 2  # one failed listing, one retry
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_vrs_generate_recovers_after_one_bad_page(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=1)
    client = _client(conn)
    outcome = fetch.fetch_virtual_report_suites(client, "parent", source=VrsSource(client))
    assert outcome.status == "healthy"
    assert sorted(v.id for v in outcome.data) == ["vrs0", "vrs1", "vrs2"]
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_vrs_summaries_recover_after_one_bad_page(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=1)
    summaries = fetch.fetch_virtual_report_suite_summaries(_client(conn))
    assert [s.id for s in summaries] == ["vrs0", "vrs1", "vrs2"]
    assert capsys.readouterr().out == ""


# --- a page that fails every time ---------------------------------------------------------


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_report_suite_listing_raises_after_budget_when_page_keeps_failing(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=99)
    with pytest.raises(ApiError, match="listing page 1"):
        fetch.fetch_report_suites_raw(_client(conn))
    assert conn.page0_calls(_RS_PATH) == _MAX_RETRIES + 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_resolve_rsid_raises_rather_than_reporting_not_found(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=99)
    with pytest.raises(ApiError) as excinfo:
        fetch.resolve_rsid(_client(conn), "rs1")
    assert type(excinfo.value).__name__ != "ReportSuiteNotFoundError"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_vrs_generate_degrades_when_page_keeps_failing(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=99)
    client = _client(conn)
    outcome = fetch.fetch_virtual_report_suites(client, "parent", source=VrsSource(client))
    assert outcome.status == "degraded"
    assert outcome.data == []
    assert conn.page0_calls(_VRS_PATH) == _MAX_RETRIES + 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_vrs_generate_without_shared_source_degrades_too(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=99)
    outcome = fetch.fetch_virtual_report_suites(_client(conn), "parent")
    assert outcome.status == "degraded"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_vrs_summaries_raise_when_page_keeps_failing(bad_body, capsys) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=99)
    with pytest.raises(ApiError):
        fetch.fetch_virtual_report_suite_summaries(_client(conn))
    assert conn.page0_calls(_VRS_PATH) == _MAX_RETRIES + 1
    assert capsys.readouterr().out == ""


# --- an empty later page is not an error ----------------------------------------------------


def test_empty_later_report_suite_page_is_not_an_error() -> None:
    conn = FakeConnector(bad_page=1, bad_body={"content": []}, fail_times=99)
    rows = fetch.fetch_report_suites_raw(_client(conn))
    assert sorted(r["rsid"] for r in rows) == ["rs0", "rs2"]
    assert conn.page0_calls(_RS_PATH) == 1


def test_empty_later_vrs_page_is_not_an_error() -> None:
    conn = FakeConnector(bad_page=1, bad_body={"content": []}, fail_times=99)
    client = _client(conn)
    outcome = fetch.fetch_virtual_report_suites(client, "parent", source=VrsSource(client))
    assert outcome.status == "healthy"
    assert sorted(v.id for v in outcome.data) == ["vrs0", "vrs2"]
    summaries = fetch.fetch_virtual_report_suite_summaries(
        _client(FakeConnector(bad_page=1, bad_body={"content": []}, fail_times=99))
    )
    assert [s.id for s in summaries] == ["vrs0", "vrs2"]


# --- page 0 is never checked: behavior matches an unguarded handle ----------------------------


def _outcome(fn) -> tuple[str, Any]:
    try:
        result = fn()
    except Exception as exc:
        return ("raised", type(exc).__name__)
    return ("returned", result)


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
@pytest.mark.parametrize("fetcher", ["report_suites", "vrs_generate", "vrs_summaries"])
def test_page0_error_behaves_as_without_the_guard(bad_body, fetcher) -> None:
    def run(guarded: bool) -> tuple[tuple[str, Any], int]:
        conn = FakeConnector(bad_page=0, bad_body=bad_body, fail_times=99)
        client = _client(conn, guarded=guarded)
        if fetcher == "report_suites":
            result = _outcome(lambda: fetch.fetch_report_suites_raw(client))
        elif fetcher == "vrs_generate":
            result = _outcome(lambda: fetch.fetch_virtual_report_suites(client, "parent", source=VrsSource(client)))
            if result[0] == "returned":
                result = ("returned", (result[1].status, result[1].data))
        else:
            result = _outcome(lambda: fetch.fetch_virtual_report_suite_summaries(client))
        return result, len(conn.calls)

    assert run(guarded=True) == run(guarded=False)


def test_page0_vrs_error_still_fast_fails_to_degraded() -> None:
    conn = FakeConnector(bad_page=0, bad_body={"error_code": "500"}, fail_times=99)
    client = _client(conn)
    outcome = fetch.fetch_virtual_report_suites(client, "parent", source=VrsSource(client))
    assert outcome.status == "degraded"
    assert len(conn.calls) == 1  # permanent shape error: no retries


# --- the guard itself ---------------------------------------------------------------------


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_non_listing_endpoint_error_body_passes_through(bad_body) -> None:
    conn = FakeConnector(bad_page=1, bad_body=bad_body, fail_times=99)
    guard = _ListingPageGuard(conn)
    endpoint = "https://example.invalid/segments"
    assert guard.getData(endpoint, {"page": 1}, headers={}) == bad_body
    assert guard.getData(endpoint + _RS_PATH + "/extra", params={"page": 1}) == bad_body


@pytest.mark.parametrize("bad_body", _ERROR_BODIES)
def test_listing_page0_error_body_passes_through_the_guard(bad_body) -> None:
    conn = FakeConnector(bad_page=0, bad_body=bad_body, fail_times=99)
    guard = _ListingPageGuard(conn)
    assert guard.getData("https://example.invalid" + _RS_PATH, params={"page": "0"}) == bad_body
    assert guard.getData("https://example.invalid" + _VRS_PATH, params={}) == bad_body
    odd = _ListingPageGuard(MagicMock(getData=MagicMock(return_value=bad_body)))
    assert odd.getData("https://example.invalid" + _VRS_PATH, params={"page": "x"}) == bad_body
    assert odd.getData("https://example.invalid" + _VRS_PATH, params="page=1") == bad_body


def test_guard_delegates_other_attributes() -> None:
    inner = MagicMock()
    guard = _ListingPageGuard(inner)
    assert guard.header is inner.header
    assert guard.config is inner.config
    guard.header = {"x": "y"}
    assert inner.header == {"x": "y"}
    bare = object.__new__(_ListingPageGuard)
    with pytest.raises(AttributeError):
        _ = bare.header  # no inner connector yet: a plain AttributeError, not a recursion


def _creds() -> Credentials:
    return Credentials(org_id="O", client_id="C", secret="S", scopes="X", source="env")


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_from_credentials_installs_the_guard(aa_module: MagicMock) -> None:
    handle = MagicMock()
    inner = handle.connector
    aa_module.Login.return_value.getCompanyId.return_value = [{"globalCompanyId": "abc123"}]
    aa_module.Analytics.return_value = handle

    client = AaClient.from_credentials(_creds())

    assert client.handle is handle
    assert isinstance(client.handle.connector, _ListingPageGuard)
    assert client.handle.connector._inner is inner


def test_installing_twice_does_not_double_wrap() -> None:
    conn = FakeConnector()
    handle = _handle(conn)
    first = handle.connector
    install_listing_page_guard(handle)
    assert handle.connector is first
    assert first._inner is conn


# --- the SDK still pages through connector.getData on the guarded paths -----------------------


def test_sdk_listing_methods_page_through_the_guarded_paths() -> None:
    """Fails loudly if an SDK upgrade renames the listing paths or stops calling connector.getData."""
    conn = FakeConnector()
    handle = _handle(conn)
    handle.getReportSuites(extended_info=True, limit=1000)
    handle.getVirtualReportSuites(extended_info=True, limit=1000)

    rs_calls = [(e, p) for e, p in conn.calls if "virtual" not in e]
    vrs_calls = [(e, p) for e, p in conn.calls if "virtual" in e]
    assert len(rs_calls) == _TOTAL_PAGES
    assert len(vrs_calls) == _TOTAL_PAGES
    assert all(e.endswith(_RS_PATH) for e, _ in rs_calls)
    assert all(e.endswith(_VRS_PATH) for e, _ in vrs_calls)
    assert sorted(int(p.get("page", 0)) for _, p in rs_calls) == [0, 1, 2]
    assert sorted(int(p.get("page", 0)) for _, p in vrs_calls) == [0, 1, 2]
    assert set(_PAGED_LISTING_PATHS) == {_RS_PATH, _VRS_PATH}
