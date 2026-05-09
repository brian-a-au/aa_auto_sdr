"""Item D from VRS hardening spec — parentRsid filter visibility."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.fetch import fetch_virtual_report_suites
from aa_auto_sdr.api.resilience import RetryPolicy


@pytest.fixture
def mock_client() -> AaClient:
    handle = MagicMock()
    return AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy())


def test_no_drops_no_debug_record(mock_client, caplog) -> None:
    """When all VRS rows match parent_rsid, no vrs_parent_filter record fires."""
    mock_client.handle.getVirtualReportSuites.return_value = pd.DataFrame(
        [
            {"id": "v1", "name": "V1", "parentRsid": "rs1"},
            {"id": "v2", "name": "V2", "parentRsid": "rs1"},
        ]
    )
    with caplog.at_level(logging.DEBUG):
        fetch_virtual_report_suites(mock_client, "rs1")
    debug_filter_records = [r for r in caplog.records if "vrs_parent_filter" in r.message]
    assert not debug_filter_records


def test_drops_emit_structured_debug(mock_client, caplog) -> None:
    """When some rows are dropped (no parent or other parent), emit a single
    DEBUG record with structured pulled/filtered/dropped_no_parent/dropped_other_parent fields."""
    mock_client.handle.getVirtualReportSuites.return_value = pd.DataFrame(
        [
            {"id": "v1", "name": "V1", "parentRsid": "rs1"},
            {"id": "v2", "name": "V2", "parentRsid": "rs2"},  # other-parent drop
            {"id": "v3", "name": "V3", "parentRsid": None},  # no-parent drop
        ]
    )
    with caplog.at_level(logging.DEBUG):
        result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "healthy"
    assert len(result.data) == 1
    debug_records = [r for r in caplog.records if "vrs_parent_filter" in r.message]
    assert len(debug_records) == 1
    rec = debug_records[0]
    assert rec.pulled == 3
    assert rec.filtered == 1
    assert rec.dropped_no_parent == 1
    assert rec.dropped_other_parent == 1
