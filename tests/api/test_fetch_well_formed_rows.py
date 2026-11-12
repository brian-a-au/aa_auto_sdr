"""Well-formed rows give the same models whatever shape guards the fetchers add.

Every fetcher runs over the `sample_rs.json` fixture, both as the plain lists
the raw SDK calls return and as the DataFrames the listing calls return, and
the models are compared with values pinned here. The values match the ones
the older per-field tests in `test_fetch.py` and `sdr/test_builder.py` pin.
A change to how malformed or null cells are read must leave this file green.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api import fetch, models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.report_suite_index import ReportSuiteIndex

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"
RSID = "demo.prod"

_SEGMENT_111_DEFINITION = {
    "func": "segment",
    "version": [1, 0, 0],
    "container": {
        "func": "container",
        "context": "hits",
        "pred": {"func": "streq", "str": "mobile", "val": {"func": "attr", "name": "variables/evar2"}},
    },
}
_SEGMENT_222_DEFINITION = {
    "func": "segment",
    "version": [1, 0, 0],
    "container": {
        "func": "container",
        "context": "visits",
        "pred": {
            "func": "and",
            "preds": [
                {"func": "gt", "num": 1, "val": {"func": "attr", "name": "variables/visitnumber"}},
                {"func": "event-exists", "evt": {"func": "event", "name": "metrics/pageviews"}},
            ],
        },
    },
}
_CM_1_DEFINITION = {
    "func": "calc-metric",
    "version": [1, 0, 0],
    "formula": {
        "func": "divide",
        "col1": {"func": "metric", "name": "metrics/orders"},
        "col2": {"func": "segment", "segment_id": "s_222", "metric": {"func": "metric", "name": "metrics/visits"}},
    },
}

EXPECTED_REPORT_SUITE = models.ReportSuite(
    rsid=RSID, name="Demo Production", timezone="US/Pacific", currency="USD", parent_rsid=None
)
EXPECTED_DIMENSIONS = [
    models.Dimension(
        id="variables/evar1",
        name="User ID",
        type="string",
        category="Conversion",
        parent="",
        pathable=False,
        description="Authenticated user identifier",
    ),
    models.Dimension(
        id="variables/evar2",
        name="Plan",
        type="string",
        category="Conversion",
        parent="",
        pathable=False,
        description=None,
    ),
    models.Dimension(
        id="variables/prop1",
        name="Page Type",
        type="string",
        category="Content",
        parent="",
        pathable=True,
        description="Section taxonomy",
        tags=["taxonomy"],
    ),
    models.Dimension(
        id="variables/events",
        name="Custom Events",
        type="counter",
        category=None,
        parent="",
        pathable=False,
        description=None,
    ),
]
EXPECTED_METRICS = [
    models.Metric(
        id="metrics/pageviews",
        name="Page Views",
        type="int",
        category="Traffic",
        precision=0,
        segmentable=True,
        description="Total page views",
    ),
    models.Metric(
        id="metrics/visits",
        name="Visits",
        type="int",
        category="Traffic",
        precision=0,
        segmentable=True,
        description=None,
    ),
    models.Metric(
        id="metrics/orders",
        name="Orders",
        type="int",
        category="Commerce",
        precision=0,
        segmentable=True,
        description="Conversion events",
        data_group="Commerce",
    ),
]
EXPECTED_SEGMENTS = [
    models.Segment(
        id="s_111",
        name="Mobile Users",
        description="Mobile device traffic",
        rsid=RSID,
        owner_id=42,
        definition=_SEGMENT_111_DEFINITION,
        created="2025-01-01T00:00:00Z",
        modified="2025-01-02T00:00:00Z",
    ),
    models.Segment(
        id="s_222",
        name="Returning Visitors",
        description=None,
        rsid=RSID,
        owner_id=42,
        definition=_SEGMENT_222_DEFINITION,
    ),
]
EXPECTED_CALCULATED_METRICS = [
    models.CalculatedMetric(
        id="cm_1",
        name="Conversion Rate",
        description="Orders divided by visits",
        rsid=RSID,
        owner_id=42,
        polarity="positive",
        precision=4,
        type="decimal",
        definition=_CM_1_DEFINITION,
        categories=["Conversion"],
    ),
]
EXPECTED_VRS = [
    models.VirtualReportSuite(
        id="vrs_eu",
        name="EU Visitors Only",
        parent_rsid=RSID,
        timezone="Europe/Berlin",
        description="EU-only traffic view",
        segment_list=["s_eu"],
        modified="2025-03-01T00:00:00Z",
    ),
]
EXPECTED_CLASSIFICATIONS = [models.ClassificationDataset(id="ds_5", name="Campaign Metadata", rsid=RSID)]


def _as_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


@pytest.fixture(params=[_as_list, pd.DataFrame], ids=["plain_list", "dataframe"])
def client(request: pytest.FixtureRequest) -> AaClient:
    shape = request.param
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = shape([raw["report_suite"]])
    handle.getDimensions.return_value = shape(raw["dimensions"])
    handle.getMetrics.return_value = shape(raw["metrics"])
    handle.getSegments.return_value = shape(raw["segments"])
    handle.getCalculatedMetrics.return_value = shape(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = shape(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = shape(raw["classification_datasets"])
    return AaClient(handle=handle, company_id="testco")


def test_report_suite_is_unchanged(client: AaClient) -> None:
    assert fetch.fetch_report_suite(client, RSID) == EXPECTED_REPORT_SUITE
    listing = fetch.fetch_report_suites_raw(client)
    assert fetch.fetch_report_suite(client, RSID, preloaded_suites=listing) == EXPECTED_REPORT_SUITE
    assert fetch.fetch_report_suite(client, RSID, preloaded_suites=ReportSuiteIndex(listing)) == EXPECTED_REPORT_SUITE


def test_component_families_are_unchanged(client: AaClient) -> None:
    assert fetch.fetch_dimensions(client, RSID) == EXPECTED_DIMENSIONS
    assert fetch.fetch_metrics(client, RSID) == EXPECTED_METRICS
    assert fetch.fetch_segments(client, RSID) == EXPECTED_SEGMENTS
    assert fetch.fetch_calculated_metrics(client, RSID) == EXPECTED_CALCULATED_METRICS


def test_graceful_degrade_families_are_unchanged(client: AaClient) -> None:
    assert fetch.fetch_virtual_report_suites(client, RSID) == models.FetchOutcome.healthy(EXPECTED_VRS)
    assert fetch.fetch_classification_datasets(client, RSID) == models.FetchOutcome.healthy(EXPECTED_CLASSIFICATIONS)


def test_discovery_listings_are_unchanged(client: AaClient) -> None:
    assert fetch.fetch_report_suite_summaries(client) == [
        models.ReportSuiteSummary(rsid=RSID, name="Demo Production"),
    ]
    assert fetch.fetch_virtual_report_suite_summaries(client) == [
        models.VirtualReportSuiteSummary(id="vrs_eu", name="EU Visitors Only", parent_rsid=RSID),
    ]


@pytest.mark.parametrize("name_match", ["exact", "insensitive", "fuzzy"])
def test_resolve_rsid_is_unchanged(client: AaClient, name_match: str) -> None:
    assert fetch.resolve_rsid(client, RSID, name_match=name_match) == ([RSID], False)
    assert fetch.resolve_rsid(client, "Demo Production", name_match=name_match) == ([RSID], True)
    listing = fetch.fetch_report_suites_raw(client)
    index = ReportSuiteIndex(listing)
    assert fetch.resolve_rsid(client, "Demo Production", name_match=name_match, preloaded_suites=index) == (
        [RSID],
        True,
    )
