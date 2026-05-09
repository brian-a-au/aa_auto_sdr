"""fetch_virtual_report_suites returns FetchOutcome — ladder mapping per spec §4.2."""

# v1.7.2 regression for count_only=False (default) running the full→minimal
# ladder unchanged: see tests/api/test_fetch_count_only.py::test_vrs_count_only_default_false_runs_existing_ladder

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api import models
from aa_auto_sdr.api.fetch import fetch_virtual_report_suites


def _vrs_row(vrs_id: str, parent: str = "rs1") -> dict:
    return {
        "id": vrs_id,
        "name": vrs_id.upper(),
        "parentRsid": parent,
        "timezone": "America/Los_Angeles",
        "description": "test",
        "segmentList": [],
        "curatedComponents": [],
        "modified": None,
    }


def _client_for_vrs(*, full_response, minimal_response=None) -> MagicMock:
    handle = MagicMock()

    def get_vrs(extended_info: bool = True) -> pd.DataFrame:
        if extended_info:
            if isinstance(full_response, Exception):
                raise full_response
            return pd.DataFrame(full_response)
        if isinstance(minimal_response, Exception):
            raise minimal_response
        return pd.DataFrame(minimal_response or [])

    handle.getVirtualReportSuites = get_vrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def test_vrs_full_expansion_returns_healthy() -> None:
    client = _client_for_vrs(full_response=[_vrs_row("v1")])
    outcome = fetch_virtual_report_suites(client, "rs1")
    assert isinstance(outcome, models.FetchOutcome)
    assert outcome.status == "healthy"
    assert outcome.expansion_level is None
    assert len(outcome.data) == 1


def test_vrs_minimal_rung_success_returns_partial_minimal() -> None:
    client = _client_for_vrs(
        full_response=KeyError("content"),
        minimal_response=[_vrs_row("v1")],
    )
    outcome = fetch_virtual_report_suites(client, "rs1")
    assert outcome.status == "partial"
    assert outcome.expansion_level == "minimal"
    assert len(outcome.data) == 1


def test_vrs_both_rungs_exhausted_returns_degraded() -> None:
    client = _client_for_vrs(
        full_response=KeyError("content"),
        minimal_response=KeyError("content"),
    )
    outcome = fetch_virtual_report_suites(client, "rs1")
    assert outcome.status == "degraded"
    assert outcome.expansion_level is None
    assert outcome.data == []
