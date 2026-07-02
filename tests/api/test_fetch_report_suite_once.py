from __future__ import annotations

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.resilience import RetryPolicy


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
