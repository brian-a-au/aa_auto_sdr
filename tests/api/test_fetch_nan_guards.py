"""NaN guards on the DataFrame-bound fetchers (dimensions / metrics / VRS).

v1.21.4 moved segments and calculated metrics to format="raw", eliminating
the NaN pollution that pandas introduces for ragged rows (absent cells become
float-NaN, which str() renders as the literal "nan" and bool() as True).
getDimensions / getMetrics / getVirtualReportSuites have no raw option in the
SDK — the DataFrame round trip is forced — so the coercion helpers must treat
float-NaN exactly like an absent key.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient


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
