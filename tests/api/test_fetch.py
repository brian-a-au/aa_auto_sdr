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
    # dataGroup=True intentionally NOT passed — the aanalytics2 wrapper crashes
    # with KeyError when the API doesn't return that column for the given RS.
    # See note in fetch_metrics() and CHANGELOG v0.1.1.
    assert "dataGroup" not in kwargs


def test_fetch_metrics_handles_missing_dataGroup_column() -> None:
    """Regression test for the v0.1.1 fix.

    Real Adobe Analytics report suites often return metrics with no `dataGroup`
    column at all (the column only appears when `getMetrics(dataGroup=True)` is
    requested AND the RS supports it). This test simulates that real-API shape:
    records have no `dataGroup` key. fetch_metrics must produce valid Metric
    instances with data_group=None — never raise KeyError."""
    handle = MagicMock()
    handle.getMetrics.return_value = _df(
        [
            {
                "id": "metrics/pageviews",
                "name": "Page Views",
                "type": "int",
                "category": "Traffic",
                "precision": 0,
                "segmentable": True,
                "description": "Total page views",
                "tags": [],
            },
            {
                "id": "metrics/visits",
                "name": "Visits",
                "type": "int",
                "category": "Traffic",
                "precision": 0,
                "segmentable": True,
                "description": None,
                "tags": [],
            },
        ]
    )
    client = AaClient(handle=handle, company_id="testco")

    mets = fetch.fetch_metrics(client, "demo.prod")

    assert len(mets) == 2
    assert all(isinstance(m, models.Metric) for m in mets)
    assert all(m.data_group is None for m in mets)
    by_id = {m.id: m for m in mets}
    assert by_id["metrics/pageviews"].category == "Traffic"
    assert by_id["metrics/pageviews"].segmentable is True


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


def test_fetch_classification_datasets_tolerates_dataSetId_keys() -> None:
    """Regression test for the v0.1.1 fix.

    The classifications API response shape varies by org/RS — some records
    use `dataSetId`/`displayName` instead of `id`/`name`. fetch_classification_datasets
    must tolerate either shape."""
    handle = MagicMock()
    handle.getClassificationDatasets.return_value = _df(
        [
            {"dataSetId": "ds_a", "displayName": "Campaign Owner", "rsid": "demo.prod"},
            {"datasetId": "ds_b", "displayName": "Campaign Type", "rsid": "demo.prod"},
        ]
    )
    client = AaClient(handle=handle, company_id="testco")

    cs = fetch.fetch_classification_datasets(client, "demo.prod")

    assert len(cs) == 2
    assert {c.id for c in cs} == {"ds_a", "ds_b"}
    assert {c.name for c in cs} == {"Campaign Owner", "Campaign Type"}


def test_fetch_classification_datasets_skips_records_without_id_keys() -> None:
    """If a record has none of the recognized id keys, skip it rather than crash."""
    handle = MagicMock()
    handle.getClassificationDatasets.return_value = _df(
        [
            {"id": "ds_keep", "name": "Keeper", "rsid": "demo.prod"},
            {"unrelatedKey": "junk", "rsid": "demo.prod"},  # no id-like key — skip
        ]
    )
    client = AaClient(handle=handle, company_id="testco")

    cs = fetch.fetch_classification_datasets(client, "demo.prod")

    assert len(cs) == 1
    assert cs[0].id == "ds_keep"


def test_fetch_classification_datasets_returns_empty_on_wrapper_error(capsys) -> None:
    """If the SDK call itself raises, return [] with a stderr warning rather
    than breaking the entire SDR pipeline (classifications are best-effort)."""
    handle = MagicMock()
    handle.getClassificationDatasets.side_effect = KeyError("['id'] not in index")
    client = AaClient(handle=handle, company_id="testco")

    cs = fetch.fetch_classification_datasets(client, "demo.prod")

    assert cs == []
    captured = capsys.readouterr()
    assert "classifications fetch failed" in captured.err


def test_fetch_report_suite_summaries_normalizes_records(mock_client: AaClient) -> None:
    """Each raw record becomes a ReportSuiteSummary with rsid + name only."""
    summaries = fetch.fetch_report_suite_summaries(mock_client)
    assert all(isinstance(s, models.ReportSuiteSummary) for s in summaries)
    assert summaries[0].rsid == "demo.prod"
    assert summaries[0].name == "Demo Production"


def test_fetch_report_suite_summaries_sort_order() -> None:
    """Output is alphabetically sorted by rsid (stable across runs)."""
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "zeta.prod", "name": "Zeta"},
            {"rsid": "alpha.prod", "name": "Alpha"},
            {"rsid": "mid.prod", "name": "Mid"},
        ],
    )
    client = AaClient(handle=handle, company_id="testco")
    summaries = fetch.fetch_report_suite_summaries(client)
    assert [s.rsid for s in summaries] == ["alpha.prod", "mid.prod", "zeta.prod"]


def test_fetch_report_suite_summaries_drops_records_with_empty_rsid() -> None:
    """Records missing `rsid` are skipped (defensive — real API returns them)."""
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "good", "name": "Good"},
            {"rsid": "", "name": "Empty"},
            {"rsid": None, "name": "None"},
        ],
    )
    client = AaClient(handle=handle, company_id="testco")
    summaries = fetch.fetch_report_suite_summaries(client)
    assert [s.rsid for s in summaries] == ["good"]


def test_fetch_report_suite_summaries_passes_extended_info(mock_client: AaClient) -> None:
    """The wrapper must request extended_info so name (and any future fields)
    are populated. Mirrors the call-shape tests for other fetchers in this file."""
    fetch.fetch_report_suite_summaries(mock_client)
    _, kwargs = mock_client.handle.getReportSuites.call_args
    assert kwargs.get("extended_info") is True


def test_fetch_virtual_report_suite_summaries_normalizes_records(mock_client: AaClient) -> None:
    """Each raw record becomes a VirtualReportSuiteSummary with id, name, parent_rsid."""
    summaries = fetch.fetch_virtual_report_suite_summaries(mock_client)
    assert all(isinstance(s, models.VirtualReportSuiteSummary) for s in summaries)
    # Fixture has at least one VRS; it should round-trip cleanly.
    if summaries:
        assert summaries[0].id
        assert summaries[0].parent_rsid is not None


def test_fetch_virtual_report_suite_summaries_sort_order() -> None:
    """Output is alphabetically sorted by id (stable across runs)."""
    handle = MagicMock()
    handle.getVirtualReportSuites.return_value = _df(
        [
            {"id": "vrs.zeta", "name": "Zeta", "parentRsid": "p1"},
            {"id": "vrs.alpha", "name": "Alpha", "parentRsid": "p2"},
            {"id": "vrs.mid", "name": "Mid", "parentRsid": "p1"},
        ],
    )
    client = AaClient(handle=handle, company_id="testco")
    summaries = fetch.fetch_virtual_report_suite_summaries(client)
    assert [s.id for s in summaries] == ["vrs.alpha", "vrs.mid", "vrs.zeta"]


def test_fetch_virtual_report_suite_summaries_passes_extended_info(mock_client: AaClient) -> None:
    """The wrapper must request extended_info so parent_rsid (and any future fields)
    are populated. Mirrors the call-shape tests for other fetchers in this file."""
    fetch.fetch_virtual_report_suite_summaries(mock_client)
    _, kwargs = mock_client.handle.getVirtualReportSuites.call_args
    assert kwargs.get("extended_info") is True
