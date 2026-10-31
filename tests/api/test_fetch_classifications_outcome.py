"""fetch_classification_datasets returns FetchOutcome — see spec §4.2."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.fetch import fetch_classification_datasets
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.sdr.builder import build_sdr

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_rs.json"


def _client_with_classifications(rows: list[dict] | Exception) -> MagicMock:
    handle = MagicMock()
    if isinstance(rows, Exception):
        handle.getClassificationDatasets.side_effect = rows
    else:
        handle.getClassificationDatasets.return_value = pd.DataFrame(rows)
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def test_classifications_healthy_returns_healthy_outcome() -> None:
    client = _client_with_classifications(
        [{"id": "ds1", "name": "Marketing channels"}],
    )
    outcome = fetch_classification_datasets(client, "rs1")
    assert isinstance(outcome, models.FetchOutcome)
    assert outcome.status == "healthy"
    assert outcome.expansion_level is None
    assert len(outcome.data) == 1
    assert outcome.data[0].id == "ds1"


def test_classifications_sdk_exception_returns_degraded_outcome() -> None:
    client = _client_with_classifications(KeyError("content"))
    outcome = fetch_classification_datasets(client, "rs1")
    assert isinstance(outcome, models.FetchOutcome)
    assert outcome.status == "degraded"
    assert outcome.expansion_level is None
    assert outcome.data == []


def test_classifications_empty_endpoint_returns_healthy_with_empty_list() -> None:
    """Empty result from a healthy endpoint is healthy, not degraded."""
    client = _client_with_classifications([])
    outcome = fetch_classification_datasets(client, "rs1")
    assert outcome.status == "healthy"
    assert outcome.data == []


def _stub_client(stub: Any, *, max_retries: int = 0) -> AaClient:
    raw = json.loads(_FIXTURE.read_text())
    h = MagicMock()
    h.getReportSuites.return_value = pd.DataFrame([raw["report_suite"]])
    h.getDimensions.return_value = raw["dimensions"]
    h.getMetrics.return_value = raw["metrics"]
    h.getSegments.return_value = raw["segments"]
    h.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    h.getVirtualReportSuites.return_value = pd.DataFrame(raw["virtual_report_suites"])
    h.getClassificationDatasets.return_value = stub
    return AaClient(
        handle=h,
        company_id="c",
        retry_policy=RetryPolicy(max_retries=max_retries, base_delay=0.001, max_delay=0.001),
    )


@pytest.mark.parametrize(
    "stub",
    [
        {"errorCode": "403", "errorDescription": "Forbidden", "errorId": "x"},
        {"error_code": "500000", "message": "internal"},
        {"error": "Request Error"},
        {"error_code": "429050"},
    ],
)
def test_classification_error_mapping_is_degraded(stub: dict) -> None:
    out = fetch_classification_datasets(_stub_client(stub), "demo.prod")
    assert out.status == "degraded"
    assert out.data == []


def test_classification_transient_stub_is_retried() -> None:
    c = _stub_client({"error": "Request Error"}, max_retries=2)
    fetch_classification_datasets(c, "demo.prod")
    assert c.handle.getClassificationDatasets.call_count == 3


def test_classification_single_record_dict_still_healthy() -> None:
    out = fetch_classification_datasets(
        _stub_client({"id": "ds1", "name": "C", "rsid": "demo.prod"}),
        "demo.prod",
    )
    assert out.status == "healthy"
    assert [d.id for d in out.data] == ["ds1"]


def test_build_sdr_records_degraded_classifications() -> None:
    doc = build_sdr(
        _stub_client({"errorCode": "403"}),
        "demo.prod",
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="t",
    )
    assert "classifications" in doc.fetch_status
