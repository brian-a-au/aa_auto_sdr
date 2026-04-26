"""Pure builder: fetch → SdrDocument with no I/O."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.sdr.builder import build_sdr

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


def _mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return AaClient(handle=handle, company_id="testco")


def test_build_sdr_returns_complete_document() -> None:
    client = _mock_client()
    captured_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    doc = build_sdr(client, "demo.prod", captured_at=captured_at, tool_version="0.1.0")

    assert doc.report_suite.rsid == "demo.prod"
    assert len(doc.dimensions) == 4
    assert len(doc.metrics) == 3
    assert len(doc.segments) == 2
    assert len(doc.calculated_metrics) == 1
    assert len(doc.virtual_report_suites) == 1
    assert len(doc.classifications) == 1  # one ClassificationDataset
    assert doc.captured_at == captured_at
    assert doc.tool_version == "0.1.0"


def test_build_sdr_components_sorted_by_id() -> None:
    client = _mock_client()
    doc = build_sdr(
        client,
        "demo.prod",
        captured_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        tool_version="0.1.0",
    )
    dim_ids = [d.id for d in doc.dimensions]
    assert dim_ids == sorted(dim_ids)
    metric_ids = [m.id for m in doc.metrics]
    assert metric_ids == sorted(metric_ids)
