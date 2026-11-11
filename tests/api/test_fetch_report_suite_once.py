from __future__ import annotations

import logging

import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.report_suite_index import ReportSuiteIndex
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError


class _Handle:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[dict] = []

    def getReportSuites(self, **kwargs):
        self.calls.append(kwargs)
        # Emulate server-side filter when rsid_list is passed.
        if kwargs.get("rsid_list"):
            return [r for r in self._rows if r["rsid"] == kwargs["rsid_list"]]
        return list(self._rows)


class _Client:
    def __init__(self, rows):
        self.handle = _Handle(rows)
        self.retry_policy = RetryPolicy()


_ROWS = [
    {"rsid": "rs1", "name": "One", "timezone": "UTC", "currency": "USD", "parentRsid": None},
    {"rsid": "rs2", "name": "Two", "timezone": "UTC", "currency": "EUR", "parentRsid": None},
]


def test_fetch_report_suite_uses_server_side_filter():
    client = _Client(_ROWS)
    rs = fetch.fetch_report_suite(client, "rs2")
    assert rs.rsid == "rs2"
    assert rs.currency == "EUR"
    assert client.handle.calls[0]["rsid_list"] == "rs2"  # not a full-org scan


def test_resolve_rsid_uses_preloaded_suites():
    client = _Client(_ROWS)
    preloaded = fetch.fetch_report_suites_raw(client)
    assert len(client.handle.calls) == 1  # one listing to build the preload

    rsids, was_name = fetch.resolve_rsid(client, "rs1", preloaded_suites=preloaded)
    assert rsids == ["rs1"]
    assert was_name is False
    assert len(client.handle.calls) == 1  # resolve made NO extra SDK call


# ---------------------------------------------------------------------------
# preloaded_suites: build the model from a listing the caller already holds
# ---------------------------------------------------------------------------


def test_preloaded_row_avoids_sdk_call():
    expected = fetch.fetch_report_suite(_Client(_ROWS), "rs2")
    client = _Client(_ROWS)
    rs = fetch.fetch_report_suite(client, "rs2", preloaded_suites=list(_ROWS))
    assert client.handle.calls == []
    assert rs == expected


def test_preloaded_miss_falls_back_to_filtered_call():
    client = _Client(_ROWS)
    rs = fetch.fetch_report_suite(client, "rs2", preloaded_suites=[_ROWS[0]])
    assert rs.rsid == "rs2"
    assert len(client.handle.calls) == 1
    assert client.handle.calls[0]["rsid_list"] == "rs2"


def test_preloaded_miss_still_raises_not_found():
    client = _Client(_ROWS)
    with pytest.raises(ReportSuiteNotFoundError, match="Report suite 'nope' not found"):
        fetch.fetch_report_suite(client, "nope", preloaded_suites=list(_ROWS))
    assert len(client.handle.calls) == 1
    assert client.handle.calls[0]["rsid_list"] == "nope"


def test_preloaded_index_is_accepted():
    client = _Client(_ROWS)
    rows = list(_ROWS)
    index = ReportSuiteIndex(rows)
    rs = fetch.fetch_report_suite(client, "rs1", preloaded_suites=index)
    assert client.handle.calls == []
    assert rs.rsid == "rs1"
    assert rs.currency == "USD"
    # Read-only: neither the rows nor the index were changed.
    assert index.rows is rows
    assert rows == _ROWS
    assert index.rsids == {"rs1", "rs2"}


def test_preloaded_non_dict_rows_are_skipped():
    client = _Client(_ROWS)
    rs = fetch.fetch_report_suite(client, "rs2", preloaded_suites=["junk", None, _ROWS[1]])
    assert client.handle.calls == []
    assert rs.rsid == "rs2"


def _assert_debug_record(records, *, rsid, count):
    matching = [r for r in records if r.getMessage().startswith("fetch_report_suite count=")]
    assert len(matching) == 1
    record = matching[0]
    assert record.levelname == "DEBUG"
    assert record.name == "aa_auto_sdr.api.fetch"
    assert record.getMessage() == f"fetch_report_suite count={count} duration_ms={record.duration_ms}"
    assert record.rsid == rsid
    assert record.count == count
    assert isinstance(record.duration_ms, int)


def test_preloaded_hit_logs_debug_record(caplog):
    client = _Client(_ROWS)
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch"):
        fetch.fetch_report_suite(client, "rs1", preloaded_suites=list(_ROWS))
    _assert_debug_record(caplog.records, rsid="rs1", count=1)


def test_resolve_rsid_listing_out_receives_the_fetched_listing(caplog):
    plain = _Client(_ROWS)
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch"):
        assert fetch.resolve_rsid(plain, "Two") == (["rs2"], True)
    plain_records = [(r.levelname, r.getMessage()) for r in caplog.records]
    caplog.clear()

    client = _Client(_ROWS)
    listing: list[dict] = []
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch"):
        assert fetch.resolve_rsid(client, "Two", listing_out=listing) == (["rs2"], True)
    assert listing == _ROWS
    assert client.handle.calls == plain.handle.calls
    # Same records in the same order as without listing_out.
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == plain_records


def test_resolve_rsid_listing_out_untouched_with_preloaded_suites():
    client = _Client(_ROWS)
    listing: list[dict] = []
    fetch.resolve_rsid(client, "rs1", preloaded_suites=list(_ROWS), listing_out=listing)
    assert listing == []
    assert client.handle.calls == []


def test_sdk_path_debug_record_has_the_same_shape(caplog):
    client = _Client(_ROWS)
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch"):
        fetch.fetch_report_suite(client, "rs1")
    _assert_debug_record(caplog.records, rsid="rs1", count=1)
