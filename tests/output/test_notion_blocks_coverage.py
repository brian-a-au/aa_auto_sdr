"""Targeted coverage for notion_blocks helpers.

Covers the dataclass-attribute path of `_val`, the segment/calc-metric/VRS/
classification branches of `_rows_for`, the unknown-key fallthrough, and the
fetch-status callout/early-return branches."""

from __future__ import annotations

import types
from datetime import UTC, datetime

from aa_auto_sdr.api import models
from aa_auto_sdr.output import notion_blocks as nb
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument


def _make_doc(**components) -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid="examplersid1",
            name="Example RS",
            timezone="UTC",
            currency="USD",
            parent_rsid=None,
        ),
        dimensions=components.get("dimensions", []),
        metrics=components.get("metrics", []),
        segments=components.get("segments", []),
        calculated_metrics=components.get("calculated_metrics", []),
        virtual_report_suites=components.get("virtual_report_suites", []),
        classifications=components.get("classifications", []),
        captured_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC),
        tool_version="1.18.0",
        fetch_status={},
        quality=None,
    )


def _segment() -> models.Segment:
    return models.Segment(id="s1", name="Mobile", description="Mobile traffic", rsid="rs", owner_id=1, definition={})


def _calc() -> models.CalculatedMetric:
    return models.CalculatedMetric(
        id="cm1",
        name="Conv Rate",
        description="orders/visits",
        rsid="rs",
        owner_id=1,
        polarity="positive",
        precision=2,
        type="decimal",
        definition={},
    )


def _vrs() -> models.VirtualReportSuite:
    return models.VirtualReportSuite(id="v1", name="EU", parent_rsid="rs", timezone="UTC", description="EU view")


def _classification() -> models.ClassificationDataset:
    return models.ClassificationDataset(id="ds1", name="Campaign Meta", rsid="rs")


def test_val_reads_attribute_from_non_dict_object() -> None:
    obj = types.SimpleNamespace(name="X")
    assert nb._val(obj, "name") == "X"
    assert nb._val(obj, "missing") is None


def test_rows_for_covers_all_component_branches() -> None:
    doc = _make_doc(
        segments=[_segment()],
        calculated_metrics=[_calc()],
        virtual_report_suites=[_vrs()],
        classifications=[_classification()],
    )
    blocks = nb.build_blocks_from_document(doc)
    headings = [b["heading_2"]["rich_text"][0]["text"]["content"] for b in blocks if b["type"] == "heading_2"]
    assert any("Segments" in h for h in headings)
    assert any("Calculated Metrics" in h for h in headings)
    assert any("Virtual Report Suites" in h for h in headings)
    assert any("Classifications" in h for h in headings)
    # The segment row content is present in a table somewhere.
    tables = [b for b in blocks if b["type"] == "table"]
    flat = [
        cell[0]["text"]["content"]
        for tbl in tables
        for child in tbl["table"]["children"]
        for cell in child["table_row"]["cells"]
    ]
    assert "Mobile" in flat
    assert "Campaign Meta" in flat


def test_rows_for_unknown_component_key_returns_empty() -> None:
    assert nb._rows_for("bogus", [{"name": "x"}]) == []


def test_fetch_status_blocks_all_healthy_returns_empty() -> None:
    out = nb._fetch_status_blocks({"metrics": {"status": "healthy", "expansion_level": None}})
    assert out == []


def test_fetch_status_blocks_partial_meta_object_renders_expansion() -> None:
    meta = FetchOutcomeMeta(status="partial", expansion_level="ids_only")
    out = nb._fetch_status_blocks({"classifications": meta})
    callout = next(b for b in out if b["type"] == "callout")
    text = callout["callout"]["rich_text"][0]["text"]["content"]
    assert "ids_only" in text
    assert callout["callout"]["icon"]["emoji"] == "⚠️"
