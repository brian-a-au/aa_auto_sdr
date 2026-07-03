"""VRS fetch always requests full expansion — reduced expansion cannot work.

The aanalytics2 SDK's getVirtualReportSuites(extended_info=False) strips every
row to {name, vrsid} — no id, no parentRsid — so the client-side parentRsid
filter in _finalize_vrs_fetch can never match a reduced-expansion row. Any
path that called extended_info=False (the v1.7.2 count_only path and the
v1.7.0 ladder's minimal fallback rung) could only ever produce zero rows:
count_only reported 0 VRS for every org, and the fallback rung burned a full
retry budget to return partial([]).

These tests use a truthful SDK double that reproduces the real shape contrast
so a revert to extended_info=False anywhere fails loudly.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.fetch import fetch_virtual_report_suites
from aa_auto_sdr.api.resilience import RetryPolicy

_FULL_ROWS = [
    {
        "id": "vrs.a",
        "name": "A",
        "parentRsid": "rs1",
        "timezone": "UTC",
        "description": "d",
        "segmentList": [],
        "curatedComponents": [],
        "modified": None,
    },
    {
        "id": "vrs.other",
        "name": "Other",
        "parentRsid": "rs999",
        "timezone": "UTC",
        "description": None,
        "segmentList": [],
        "curatedComponents": [],
        "modified": None,
    },
]


def _truthful_client(*, full_error: Exception | None = None) -> AaClient:
    """SDK double reproducing the real shape contrast between expansions."""
    calls: list[bool] = []

    def gvrs(extended_info: bool = False, limit: int = 100) -> pd.DataFrame:
        calls.append(extended_info)
        if extended_info:
            if full_error is not None:
                raise full_error
            return pd.DataFrame(_FULL_ROWS)
        # Real SDK strips reduced-expansion rows to name + vrsid ONLY.
        return pd.DataFrame([{"name": r["name"], "vrsid": r["id"]} for r in _FULL_ROWS])

    handle = MagicMock()
    handle.getVirtualReportSuites = gvrs
    client = AaClient(handle=handle, company_id="testco", retry_policy=RetryPolicy(max_retries=0))
    client.handle.calls = calls  # type: ignore[attr-defined]
    return client


def test_count_only_requests_full_expansion_so_counts_work() -> None:
    """count_only must use extended_info=True — the reduced shape has no
    parentRsid, so counts were structurally always zero before."""
    client = _truthful_client()
    outcome = fetch_virtual_report_suites(client, "rs1", count_only=True)
    assert outcome.status == "healthy"
    assert outcome.expansion_level is None
    assert [v.id for v in outcome.data] == ["vrs.a"]
    assert client.handle.calls == [True], "count_only must be a single full-expansion call"


def test_count_only_failure_still_degrades_in_one_call() -> None:
    client = _truthful_client(full_error=ValueError("boom"))
    outcome = fetch_virtual_report_suites(client, "rs1", count_only=True)
    assert outcome.status == "degraded"
    assert outcome.data == []
    assert client.handle.calls == [True]


def test_full_exhaustion_degrades_without_reduced_expansion_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """The minimal fallback rung is gone: full-rung exhaustion degrades
    directly, never calls extended_info=False, and never emits
    vrs_expansion_fallback."""
    client = _truthful_client(full_error=ValueError("boom"))
    with caplog.at_level(logging.WARNING):
        outcome = fetch_virtual_report_suites(client, "rs1")
    assert outcome.status == "degraded"
    assert outcome.expansion_level is None
    assert client.handle.calls == [True], "no reduced-expansion fallback call"
    assert not any("vrs_expansion_fallback" in r.message for r in caplog.records)


def test_generate_path_uses_full_expansion_only() -> None:
    client = _truthful_client()
    outcome = fetch_virtual_report_suites(client, "rs1")
    assert outcome.status == "healthy"
    assert [v.id for v in outcome.data] == ["vrs.a"]
    assert client.handle.calls == [True]
