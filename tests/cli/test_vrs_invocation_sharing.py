"""Command-level coverage for invocation-scoped VRS enumeration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.cli.commands import inventory, stats


@pytest.mark.parametrize("command", [stats, inventory], ids=["stats", "inventory"])
def test_vrs_enumerated_once_per_command_invocation(command, monkeypatch, capsys) -> None:
    handle = MagicMock()
    handle.getVirtualReportSuites.return_value = [
        {"id": "vrs-a1", "name": "A One", "parentRsid": "rs-a"},
        {"id": "vrs-a2", "name": "A Two", "parentRsid": "rs-a"},
        {"id": "vrs-b1", "name": "B One", "parentRsid": "rs-b"},
    ]
    client = AaClient(handle=handle, company_id="company", retry_policy=RetryPolicy(max_retries=0))
    monkeypatch.setattr(command.credentials, "resolve", lambda **_: object())
    monkeypatch.setattr(command.AaClient, "from_credentials", lambda *_, **__: client)
    monkeypatch.setattr(command.fetch, "fetch_report_suites_raw", lambda _: [])
    monkeypatch.setattr(command.fetch, "resolve_rsid", lambda _, ident, **__: ([ident], False))
    monkeypatch.setattr(
        command.fetch,
        "fetch_report_suite",
        lambda _, rsid: models.ReportSuite(rsid=rsid, name=rsid, timezone="UTC", currency="USD", parent_rsid=None),
    )
    for name in ("fetch_dimensions", "fetch_metrics", "fetch_segments", "fetch_calculated_metrics"):
        monkeypatch.setattr(command.fetch, name, lambda *_: [])
    monkeypatch.setattr(
        command.fetch, "fetch_classification_datasets", lambda *_, **__: models.FetchOutcome.healthy([])
    )

    for invocation in (1, 2):
        assert command.run(rsids=["rs-a", "rs-b"], profile=None, format_name="json") == 0
        output = json.loads(capsys.readouterr().out)
        rows = output if command is stats else output["per_rsid"]
        assert {row["rsid"]: row["counts"]["virtual_report_suites"] for row in rows} == {
            "rs-a": 2,
            "rs-b": 1,
        }
        assert all("fetch_status" not in row for row in rows)
        if command is inventory:
            assert output["report_suites_count"] == 2
            assert output["totals"]["virtual_report_suites"] == 3
        assert handle.getVirtualReportSuites.call_count == invocation
        assert all(
            call.kwargs == {"extended_info": True, "limit": 1000}
            for call in handle.getVirtualReportSuites.call_args_list
        )


def _describe_client(monkeypatch, vrs_side_effect) -> AaClient:
    from aa_auto_sdr.cli.commands import inspect

    suites = [{"rsid": "rs-a", "name": "Shop"}, {"rsid": "rs-b", "name": "shop"}, {"rsid": "rs-c", "name": "Other"}]
    handle = MagicMock()
    handle.getReportSuites.side_effect = lambda rsid_list=None, **_: [
        s for s in suites if rsid_list is None or s["rsid"] == rsid_list
    ]
    handle.getVirtualReportSuites.side_effect = vrs_side_effect
    for method in ("getDimensions", "getMetrics", "getSegments", "getCalculatedMetrics", "getClassificationDatasets"):
        getattr(handle, method).return_value = []
    client = AaClient(handle=handle, company_id="company", retry_policy=RetryPolicy(max_retries=0))
    monkeypatch.setattr(inspect.credentials, "resolve", lambda **_: object())
    monkeypatch.setattr(inspect.AaClient, "from_credentials", lambda *_, **__: client)
    return client


def test_describe_multi_match_fetches_vrs_listing_once(monkeypatch, capsys) -> None:
    from aa_auto_sdr.cli.commands import inspect

    vrs_rows = [
        {"id": "vrs-a1", "name": "A One", "parentRsid": "rs-a"},
        {"id": "vrs-a2", "name": "A Two", "parentRsid": "rs-a"},
        {"id": "vrs-b1", "name": "B One", "parentRsid": "rs-b"},
    ]
    client = _describe_client(monkeypatch, lambda **_: list(vrs_rows))

    rc = inspect.run_describe_reportsuite(identifier="shop", profile=None, format_name="json", output="-")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert {row["rsid"]: row["virtual_report_suites"] for row in rows} == {"rs-a": 2, "rs-b": 1}
    assert all("fetch_status" not in row for row in rows)
    assert client.handle.getVirtualReportSuites.call_count == 1


def test_describe_multi_match_retries_vrs_listing_after_a_failure(monkeypatch, capsys) -> None:
    """A failed shared flight is forgotten, so the next suite lists again, as
    it did with one listing per suite: the first suite degrades, the second
    still gets its count."""
    from aa_auto_sdr.cli.commands import inspect

    calls: list[int] = []

    def _vrs(**_):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("vrs endpoint down")
        return [{"id": "vrs-b1", "name": "B One", "parentRsid": "rs-b"}]

    _describe_client(monkeypatch, _vrs)

    rc = inspect.run_describe_reportsuite(identifier="shop", profile=None, format_name="json", output="-")
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["rsid"] == "rs-a"
    assert rows[0]["fetch_status"]["virtual_report_suites"]["status"] == "degraded"
    assert rows[1]["rsid"] == "rs-b"
    assert rows[1]["virtual_report_suites"] == 1
    assert "fetch_status" not in rows[1]
    assert len(calls) == 2
