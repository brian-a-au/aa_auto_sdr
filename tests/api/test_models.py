"""Normalized SDK-agnostic component dataclasses."""

import pytest

from aa_auto_sdr.api import models


def test_reportsuite_holds_identity_and_metadata() -> None:
    rs = models.ReportSuite(
        rsid="abc.prod",
        name="Production",
        timezone="US/Pacific",
        currency="USD",
        parent_rsid=None,
    )
    assert rs.rsid == "abc.prod"
    assert rs.timezone == "US/Pacific"
    assert rs.parent_rsid is None


def test_dimension_minimal_construction() -> None:
    d = models.Dimension(
        id="variables/evar1",
        name="User ID",
        type="string",
        category="Conversion",
        parent="",
        pathable=False,
        description=None,
        tags=[],
        extra={},
    )
    assert d.id == "variables/evar1"
    assert d.type == "string"
    assert d.pathable is False


def test_metric_minimal_construction() -> None:
    m = models.Metric(
        id="metrics/pageviews",
        name="Page Views",
        type="int",
        category="Traffic",
        precision=0,
        segmentable=True,
        description=None,
        tags=[],
        data_group=None,
        extra={},
    )
    assert m.id == "metrics/pageviews"
    assert m.segmentable is True


def test_segment_carries_definition() -> None:
    s = models.Segment(
        id="s_123",
        name="Mobile",
        description=None,
        rsid="abc.prod",
        owner_id=42,
        definition={"hits": "..."},
        compatibility={},
        tags=[],
        created=None,
        modified=None,
        extra={},
    )
    assert s.id == "s_123"
    assert s.definition == {"hits": "..."}


def test_calculated_metric_carries_definition() -> None:
    cm = models.CalculatedMetric(
        id="cm_1",
        name="Conv Rate",
        description=None,
        rsid="abc.prod",
        owner_id=42,
        polarity="positive",
        precision=0,
        type="decimal",
        definition={"func": "divide"},
        tags=[],
        categories=[],
        extra={},
    )
    assert cm.id == "cm_1"
    assert cm.definition == {"func": "divide"}


def test_virtual_report_suite_minimal_construction() -> None:
    vrs = models.VirtualReportSuite(
        id="vrs_1",
        name="EU Only",
        parent_rsid="parent.prod",
        timezone=None,
        description=None,
        segment_list=["s1"],
        curated_components=[],
        modified=None,
        extra={},
    )
    assert vrs.parent_rsid == "parent.prod"


def test_classification_dataset_minimal_construction() -> None:
    """Renamed from `Classification` — API 2.0 exposes dataset-level shape only.

    See spike findings §4: API 2.0 has no list-classifications-on-dimension
    endpoint; only dataset enumeration via getClassificationDatasets(rsid).
    """
    c = models.ClassificationDataset(
        id="ds_5",
        name="Campaign Metadata",
        rsid="abc.prod",
        extra={},
    )
    assert c.id == "ds_5"
    assert c.rsid == "abc.prod"


@pytest.mark.parametrize(
    "cls,kwargs",
    [
        (
            models.ReportSuite,
            {
                "rsid": "x",
                "name": "n",
                "timezone": "T",
                "currency": "USD",
                "parent_rsid": None,
            },
        ),
        (
            models.Dimension,
            {
                "id": "x",
                "name": "n",
                "type": "t",
                "category": "c",
                "parent": "",
                "pathable": False,
                "description": None,
                "tags": [],
                "extra": {},
            },
        ),
        (
            models.Metric,
            {
                "id": "x",
                "name": "n",
                "type": "t",
                "category": "c",
                "precision": 0,
                "segmentable": True,
                "description": None,
                "tags": [],
                "data_group": None,
                "extra": {},
            },
        ),
    ],
)
def test_models_are_frozen(cls, kwargs) -> None:
    instance = cls(**kwargs)
    with pytest.raises((AttributeError, Exception)):
        instance.name = "modified"  # type: ignore[misc]
