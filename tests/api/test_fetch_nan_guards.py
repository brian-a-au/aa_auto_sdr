"""NaN guards for DataFrame compatibility and VRS normalization.

Dimensions and metrics now request raw SDK responses, but their boundary still
accepts DataFrames. VRS also uses DataFrames, where ragged rows introduce NaN;
coercion helpers must treat float-NaN exactly like an absent key.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError


def _client(**frames: pd.DataFrame) -> AaClient:
    handle = MagicMock()
    for method, frame in frames.items():
        getattr(handle, method).return_value = frame
    return AaClient(handle=handle, company_id="testco")


def test_dimension_missing_cells_resolve_to_defaults_not_nan() -> None:
    """A row missing description/tags/parent/pathable/type/category gets model
    defaults, not 'nan' strings / True / [nan]."""
    frame = pd.DataFrame(
        [
            {
                "id": "evar1",
                "name": "Campaign",
                "type": "string",
                "category": "Conversion",
                "parent": "",
                "pathable": False,
                "description": "utm",
                "tags": ["a"],
            },
            {"id": "evar2", "name": "Bare"},
        ],
    )
    client = _client(getDimensions=frame)
    dims = fetch.fetch_dimensions(client, "rs1")
    bare = next(d for d in dims if d.id == "evar2")
    assert bare.description is None
    assert bare.tags == []
    assert bare.parent == ""
    assert bare.pathable is False
    assert bare.type == "unknown"
    assert bare.category is None


def test_metric_missing_cells_resolve_to_defaults_not_nan() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": "event1",
                "name": "Orders",
                "type": "int",
                "category": "Conversion",
                "precision": 0,
                "segmentable": True,
                "description": "orders",
                "tags": [],
            },
            {"id": "event2", "name": "Bare"},
        ],
    )
    client = _client(getMetrics=frame)
    metrics = fetch.fetch_metrics(client, "rs1")
    bare = next(m for m in metrics if m.id == "event2")
    assert bare.description is None
    assert bare.tags == []
    assert bare.segmentable is False
    assert bare.type == "unknown"
    assert bare.data_group is None


def test_metric_nan_name_falls_back_to_id() -> None:
    frame = pd.DataFrame(
        [
            {"id": "event1", "name": "Orders", "description": "x"},
            {"id": "event2", "description": "y"},  # name cell becomes NaN
        ],
    )
    client = _client(getMetrics=frame)
    metrics = fetch.fetch_metrics(client, "rs1")
    bare = next(m for m in metrics if m.id == "event2")
    assert bare.name == "event2"


def test_vrs_missing_cells_resolve_to_defaults_not_nan() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": "vrs.full",
                "name": "Full",
                "parentRsid": "rs1",
                "timezone": "UTC",
                "description": "d",
                "segmentList": ["s1"],
                "curatedComponents": [],
                "modified": "2026-01-01",
            },
            {"id": "vrs.bare", "name": "Bare", "parentRsid": "rs1"},
        ],
    )
    client = _client(getVirtualReportSuites=frame)
    outcome = fetch.fetch_virtual_report_suites(client, "rs1")
    bare = next(v for v in outcome.data if v.id == "vrs.bare")
    assert bare.description is None
    assert bare.timezone is None
    assert bare.segment_list == []
    assert bare.curated_components == []
    assert bare.modified is None


def test_report_suite_nan_metadata_resolves_to_none() -> None:
    frame = pd.DataFrame(
        [
            {"rsid": "rs.other", "name": "Other", "timezone": "UTC", "currency": "USD", "parentRsid": "p"},
            {"rsid": "rs1", "name": "Target"},
        ],
    )
    client = _client(getReportSuites=frame)
    rs = fetch.fetch_report_suite(client, "rs1")
    assert rs.timezone is None
    assert rs.currency is None
    assert rs.parent_rsid is None


def test_extra_dict_drops_nan_cells() -> None:
    """Unknown ragged columns (e.g. extraTitleInfo on some rows only) must not
    carry NaN into the extra passthrough dict — json.dump would emit a bare
    NaN token, which is invalid strict JSON in snapshots."""
    import math

    frame = pd.DataFrame(
        [
            {"id": "evar1", "name": "A", "extraTitleInfo": "t"},
            {"id": "evar2", "name": "B"},  # extraTitleInfo cell becomes NaN
        ],
    )
    client = _client(getDimensions=frame)
    dims = fetch.fetch_dimensions(client, "rs1")
    keeps = next(d for d in dims if d.id == "evar1")
    bare = next(d for d in dims if d.id == "evar2")
    assert keeps.extra["extraTitleInfo"] == "t"
    assert "extraTitleInfo" not in bare.extra
    assert not any(isinstance(v, float) and math.isnan(v) for v in bare.extra.values())


@pytest.mark.parametrize("ident", ["nan", "NaN"])
@pytest.mark.parametrize("name_match", ["insensitive", "fuzzy"])
def test_nan_identifier_does_not_match_unnamed_suite(ident: str, name_match: str) -> None:
    """A suite with no name reads as float NaN; str(NaN) is 'nan', which must
    not match a user identifier of 'nan'."""
    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame([{"rsid": "a", "name": "Shop"}, {"rsid": "b"}])
    with pytest.raises(ReportSuiteNotFoundError):
        fetch.resolve_rsid(AaClient(handle=handle, company_id="testco"), ident, name_match=name_match)


def test_vrs_summaries_missing_parent_and_id_are_not_nan() -> None:
    handle = MagicMock()
    handle.getVirtualReportSuites.return_value = pd.DataFrame(
        [
            {"id": "vrs_a", "name": "A", "parentRsid": "rs1"},
            {"id": "vrs_b", "name": "B"},
            {"name": "no id"},
        ]
    )
    summaries = fetch.fetch_virtual_report_suite_summaries(AaClient(handle=handle, company_id="c"))
    assert [(s.id, s.parent_rsid) for s in summaries] == [("vrs_a", "rs1"), ("vrs_b", "")]


# The listing row and the rsid_list= response for the same suite must give the
# same model: name falls back to the rsid, timezone falls back to
# timezoneZoneinfo, and NaN cells (ragged DataFrame rows) become None.
_SAME_ROW_CASES = [
    {"rsid": "rs1", "name": "Target", "timezone": "UTC", "currency": "USD", "parentRsid": "p"},
    {"rsid": "rs1"},
    {"rsid": "rs1", "name": float("nan"), "timezone": float("nan"), "currency": float("nan")},
    {"rsid": "rs1", "name": "T", "timezone": float("nan"), "timezoneZoneinfo": "Europe/Paris"},
    {"rsid": "rs1", "name": "T", "timezone": "  ", "timezoneZoneinfo": "Asia/Tokyo", "parentRsid": ""},
    {"rsid": "rs1", "name": "T", "currency": float("nan"), "parentRsid": float("nan"), "timezone": float("nan")},
]


@pytest.mark.parametrize("row", _SAME_ROW_CASES)
def test_listing_row_and_filtered_call_build_the_same_model(row: dict) -> None:
    other = {"rsid": "rs.other", "name": "Other", "timezone": "UTC", "currency": "USD", "parentRsid": "x"}
    # SDK path: the filtered call returns just this row.
    from_sdk = fetch.fetch_report_suite(_client(getReportSuites=pd.DataFrame([row])), "rs1")
    # Listing path: the same row inside a ragged multi-row listing frame.
    listing_client = _client(getReportSuites=pd.DataFrame([other, row]))
    listing = fetch.fetch_report_suites_raw(listing_client)
    listing_client.handle.getReportSuites.reset_mock()
    from_listing = fetch.fetch_report_suite(listing_client, "rs1", preloaded_suites=listing)
    listing_client.handle.getReportSuites.assert_not_called()
    assert from_listing == from_sdk
    # The same raw dict through both paths, with no DataFrame in between.
    plain_client = _client(getReportSuites=[dict(row)])
    from_plain_sdk = fetch.fetch_report_suite(plain_client, "rs1")
    assert fetch.fetch_report_suite(plain_client, "rs1", preloaded_suites=[dict(row)]) == from_plain_sdk
    assert from_plain_sdk == from_sdk


def test_preloaded_row_with_nan_cells_matches_sdk_path() -> None:
    nan = float("nan")
    row = {"rsid": "rs1", "name": "Target", "currency": nan, "parentRsid": nan, "timezone": nan}
    client = _client(getReportSuites=pd.DataFrame([row]))
    rs = fetch.fetch_report_suite(client, "rs1", preloaded_suites=[row])
    client.handle.getReportSuites.assert_not_called()
    assert rs.currency is None
    assert rs.parent_rsid is None
    assert rs.timezone is None
    assert rs == fetch.fetch_report_suite(client, "rs1")
