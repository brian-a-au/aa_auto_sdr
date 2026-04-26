"""Fetcher tests use a mocked AaClient with DataFrame-shaped responses
matching what aanalytics2 actually returns."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api import fetch, models
from aa_auto_sdr.api.client import AaClient

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    """The SDK returns DataFrames; fixture is JSON for readability, so coerce."""
    return pd.DataFrame(records)


@pytest.fixture
def mock_client() -> AaClient:
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


def test_fetch_report_suite_returns_normalized(mock_client: AaClient) -> None:
    rs = fetch.fetch_report_suite(mock_client, "demo.prod")
    assert isinstance(rs, models.ReportSuite)
    assert rs.rsid == "demo.prod"
    assert rs.name == "Demo Production"
    assert rs.currency == "USD"


def test_fetch_dimensions_returns_list_with_full_fields(mock_client: AaClient) -> None:
    dims = fetch.fetch_dimensions(mock_client, "demo.prod")
    assert len(dims) == 4
    assert all(isinstance(d, models.Dimension) for d in dims)
    by_id = {d.id: d for d in dims}
    assert by_id["variables/evar1"].category == "Conversion"
    assert by_id["variables/evar1"].description == "Authenticated user identifier"
    assert by_id["variables/prop1"].pathable is True
    assert by_id["variables/prop1"].tags == ["taxonomy"]


def test_fetch_dimensions_passes_richer_info_flags(mock_client: AaClient) -> None:
    fetch.fetch_dimensions(mock_client, "demo.prod")
    mock_client.handle.getDimensions.assert_called_once()
    _, kwargs = mock_client.handle.getDimensions.call_args
    assert kwargs.get("rsid") == "demo.prod"
    assert kwargs.get("description") is True
    assert kwargs.get("tags") is True


def test_fetch_metrics_returns_list_with_full_fields(mock_client: AaClient) -> None:
    mets = fetch.fetch_metrics(mock_client, "demo.prod")
    assert len(mets) == 3
    by_id = {m.id: m for m in mets}
    assert by_id["metrics/orders"].category == "Commerce"
    assert by_id["metrics/orders"].data_group == "Commerce"
    assert by_id["metrics/orders"].segmentable is True


def test_fetch_metrics_passes_richer_info_flags(mock_client: AaClient) -> None:
    fetch.fetch_metrics(mock_client, "demo.prod")
    _, kwargs = mock_client.handle.getMetrics.call_args
    assert kwargs.get("rsid") == "demo.prod"
    assert kwargs.get("description") is True
    assert kwargs.get("tags") is True
    assert kwargs.get("dataGroup") is True


def test_fetch_segments_includes_definition(mock_client: AaClient) -> None:
    segs = fetch.fetch_segments(mock_client, "demo.prod")
    assert len(segs) == 2
    by_id = {s.id: s for s in segs}
    assert by_id["s_111"].definition  # non-empty
    assert by_id["s_111"].owner_id == 42
    assert by_id["s_111"].rsid == "demo.prod"


def test_fetch_segments_passes_extended_info(mock_client: AaClient) -> None:
    fetch.fetch_segments(mock_client, "demo.prod")
    _, kwargs = mock_client.handle.getSegments.call_args
    assert kwargs.get("extended_info") is True


def test_fetch_calculated_metrics_includes_definition(mock_client: AaClient) -> None:
    cms = fetch.fetch_calculated_metrics(mock_client, "demo.prod")
    assert len(cms) == 1
    cm = cms[0]
    assert cm.name == "Conversion Rate"
    assert cm.definition  # non-empty
    assert cm.polarity == "positive"


def test_fetch_calculated_metrics_passes_extended_info(mock_client: AaClient) -> None:
    fetch.fetch_calculated_metrics(mock_client, "demo.prod")
    _, kwargs = mock_client.handle.getCalculatedMetrics.call_args
    assert kwargs.get("extended_info") is True


def test_fetch_virtual_report_suites_filters_by_parent(mock_client: AaClient) -> None:
    vrs = fetch.fetch_virtual_report_suites(mock_client, "demo.prod")
    assert len(vrs) == 1
    assert vrs[0].parent_rsid == "demo.prod"
    assert vrs[0].segment_list == ["s_eu"]


def test_fetch_virtual_report_suites_passes_extended_info(mock_client: AaClient) -> None:
    fetch.fetch_virtual_report_suites(mock_client, "demo.prod")
    _, kwargs = mock_client.handle.getVirtualReportSuites.call_args
    assert kwargs.get("extended_info") is True


def test_fetch_classification_datasets_returns_list(mock_client: AaClient) -> None:
    cs = fetch.fetch_classification_datasets(mock_client, "demo.prod")
    assert len(cs) == 1
    assert isinstance(cs[0], models.ClassificationDataset)
    assert cs[0].id == "ds_5"
    assert cs[0].rsid == "demo.prod"


def test_fetch_classification_datasets_calls_correct_method(mock_client: AaClient) -> None:
    fetch.fetch_classification_datasets(mock_client, "demo.prod")
    mock_client.handle.getClassificationDatasets.assert_called_once_with(rsid="demo.prod")
