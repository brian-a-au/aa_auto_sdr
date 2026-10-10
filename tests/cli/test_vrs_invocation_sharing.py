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
