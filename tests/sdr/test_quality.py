"""Naming audit + stale detection — pure functions over component bundles.

See spec §3.2 + §4.1.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api.models import (
    CalculatedMetric,
    ClassificationDataset,
    Dimension,
    Metric,
    Segment,
    VirtualReportSuite,
)
from aa_auto_sdr.sdr.quality import (
    audit_naming,
    detect_stale,
)


def _bundle(
    *,
    dimensions: list[Dimension] | None = None,
    metrics: list[Metric] | None = None,
    segments: list[Segment] | None = None,
    calculated_metrics: list[CalculatedMetric] | None = None,
    classifications: list[ClassificationDataset] | None = None,
    virtual_report_suites: list[VirtualReportSuite] | None = None,
) -> MagicMock:
    """Build a bundle-shaped mock matching SdrDocument's component attrs."""
    b = MagicMock()
    b.dimensions = dimensions or []
    b.metrics = metrics or []
    b.segments = segments or []
    b.calculated_metrics = calculated_metrics or []
    b.classifications = classifications or []
    b.virtual_report_suites = virtual_report_suites or []
    return b


def _dim(id_: str, name: str) -> Dimension:
    return Dimension(
        id=id_,
        name=name,
        type="string",
        category=None,
        parent="",
        pathable=False,
        description=None,
    )


def _metric(id_: str, name: str) -> Metric:
    return Metric(
        id=id_,
        name=name,
        type="int",
        category=None,
        precision=0,
        segmentable=True,
        description=None,
    )


def _segment(id_: str, name: str) -> Segment:
    return Segment(
        id=id_,
        name=name,
        description=None,
        rsid="rs1",
        owner_id=1,
        definition={},
    )


def _cm(id_: str, name: str) -> CalculatedMetric:
    return CalculatedMetric(
        id=id_,
        name=name,
        description=None,
        rsid="rs1",
        owner_id=1,
        polarity="positive",
        precision=0,
        type="calculatedMetric",
        definition={},
    )


def _cls(id_: str, name: str) -> ClassificationDataset:
    return ClassificationDataset(id=id_, name=name, rsid="rs1")


# audit_naming -------------------------------------------------------------


def test_audit_naming_counts_case_styles() -> None:
    bundle = _bundle(
        dimensions=[
            _dim("evar1", "snake_case_name"),
            _dim("evar2", "camelCaseName"),
            _dim("evar3", "PascalCaseName"),
            _dim("evar4", "1numeric_first"),
        ],
    )
    audit = audit_naming(bundle)
    assert audit["case_styles"]["snake_case"] == 1
    assert audit["case_styles"]["camelCase"] == 1
    assert audit["case_styles"]["PascalCase"] == 1
    assert audit["case_styles"]["other"] == 1


def test_audit_naming_detects_prefix_groups() -> None:
    bundle = _bundle(
        dimensions=[
            _dim("evar1", "evar_customer_id"),
            _dim("evar2", "evar_session"),
        ],
        metrics=[
            _metric("event1", "event_purchase"),
        ],
    )
    audit = audit_naming(bundle)
    assert audit["prefix_groups"].get("evar") == 2
    assert audit["prefix_groups"].get("event") == 1


def test_audit_naming_recommendations_on_mixed_styles() -> None:
    components: list[Dimension] = []
    components.extend(_dim(f"evar{i}", f"camel{i}Name") for i in range(9))
    components.append(_dim("evar9", "snake_case_name"))
    bundle = _bundle(dimensions=components)
    audit = audit_naming(bundle)
    assert any("mixed" in r.lower() or "standardiz" in r.lower() for r in audit["recommendations"])


def test_audit_naming_no_recommendations_when_consistent() -> None:
    bundle = _bundle(
        dimensions=[_dim(f"evar{i}", f"camel{i}Name") for i in range(10)],
    )
    audit = audit_naming(bundle)
    assert audit["recommendations"] == []


def test_audit_naming_handles_unicode_names() -> None:
    bundle = _bundle(
        dimensions=[_dim("evar1", "снейк_кейс_имя")],  # Cyrillic
    )
    audit = audit_naming(bundle)  # must not raise
    assert audit["total_components"] == 1


def test_audit_naming_total_components_counts_all_types() -> None:
    bundle = _bundle(
        dimensions=[_dim("evar1", "Foo")],
        metrics=[_metric("event1", "Bar")],
        segments=[_segment("s1", "Baz")],
        calculated_metrics=[_cm("cm1", "Qux")],
        classifications=[_cls("cls1", "Quux")],
    )
    audit = audit_naming(bundle)
    assert audit["total_components"] == 5  # VRS not counted (rsid-scoped, not user-named the same way)


def test_audit_naming_empty_bundle() -> None:
    bundle = _bundle()
    audit = audit_naming(bundle)
    assert audit["total_components"] == 0
    assert audit["case_styles"] == {"snake_case": 0, "camelCase": 0, "PascalCase": 0, "other": 0}


def test_audit_naming_classifies_allcaps_as_other() -> None:
    """ALLCAPS names are 'other', not PascalCase. AA names like RSID, ORDERS, CMS."""
    bundle = _bundle(
        dimensions=[
            _dim("evar1", "RSID"),
            _dim("evar2", "ORDERS"),
            _dim("evar3", "ALL_CAPS"),
        ],
    )
    audit = audit_naming(bundle)
    assert audit["case_styles"]["other"] == 3
    assert audit["case_styles"]["PascalCase"] == 0


# detect_stale -------------------------------------------------------------


def test_detect_stale_keyword_old() -> None:
    bundle = _bundle(dimensions=[_dim("evar1", "old_customer_id")])
    stales = detect_stale(bundle)
    assert len(stales) == 1
    assert "old" in str(stales[0]["reasons"]).lower()


def test_detect_stale_keyword_test() -> None:
    bundle = _bundle(metrics=[_metric("event1", "test_purchase")])
    stales = detect_stale(bundle)
    assert len(stales) == 1


def test_detect_stale_keyword_deprecated() -> None:
    bundle = _bundle(segments=[_segment("s1", "deprecated_segment")])
    stales = detect_stale(bundle)
    assert len(stales) == 1


def test_detect_stale_version_suffix_v2() -> None:
    bundle = _bundle(metrics=[_metric("event1", "purchase_v2")])
    stales = detect_stale(bundle)
    assert len(stales) == 1
    assert any("version" in r for r in stales[0]["reasons"])


def test_detect_stale_version_suffix_v10() -> None:
    bundle = _bundle(dimensions=[_dim("evar1", "evar3_v10")])
    stales = detect_stale(bundle)
    assert len(stales) == 1


def test_detect_stale_date_pattern_compact() -> None:
    bundle = _bundle(dimensions=[_dim("evar1", "evar_20240515")])
    stales = detect_stale(bundle)
    assert len(stales) == 1
    assert any("date" in r for r in stales[0]["reasons"])


def test_detect_stale_date_pattern_dashes() -> None:
    bundle = _bundle(metrics=[_metric("event1", "event_2023-12-31")])
    stales = detect_stale(bundle)
    assert len(stales) == 1


def test_detect_stale_multi_reason() -> None:
    bundle = _bundle(metrics=[_metric("event1", "test_purchase_v2")])
    stales = detect_stale(bundle)
    assert len(stales) == 1
    assert len(stales[0]["reasons"]) >= 2  # stale_keyword:test + version_suffix:v2


def test_detect_stale_no_false_positives() -> None:
    bundle = _bundle(
        dimensions=[
            _dim("evar1", "customer_id"),
            _dim("evar2", "session_count"),
        ],
        metrics=[_metric("event1", "page_view")],
    )
    stales = detect_stale(bundle)
    assert stales == []


def test_detect_stale_includes_id_name_type() -> None:
    bundle = _bundle(dimensions=[_dim("evar1", "old_thing")])
    stales = detect_stale(bundle)
    assert stales[0]["id"] == "evar1"
    assert stales[0]["name"] == "old_thing"
    assert stales[0]["type"] == "dimension"


# Purity -------------------------------------------------------------------


def test_audit_naming_pure_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """audit_naming must not invoke any AaClient method or open any file."""
    import aa_auto_sdr.sdr.quality as q

    open_calls = []
    real_open = open

    def trap_open(*a, **kw):
        open_calls.append(a)
        return real_open(*a, **kw)

    monkeypatch.setattr("builtins.open", trap_open)
    bundle = _bundle(dimensions=[_dim("evar1", "Foo")])
    q.audit_naming(bundle)
    assert open_calls == []


def test_detect_stale_pure_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.sdr.quality as q

    open_calls = []
    real_open = open

    def trap_open(*a, **kw):
        open_calls.append(a)
        return real_open(*a, **kw)

    monkeypatch.setattr("builtins.open", trap_open)
    bundle = _bundle(dimensions=[_dim("evar1", "old_thing")])
    q.detect_stale(bundle)
    assert open_calls == []
