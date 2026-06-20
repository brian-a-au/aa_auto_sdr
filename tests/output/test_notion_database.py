"""Tests for the Notion SDR Registry database row builder + upsert."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument


def _make_doc(
    *,
    quality: dict | None = None,
    fetch_status: dict | None = None,
    name: str = "Example RS",
) -> SdrDocument:
    rs = models.ReportSuite(
        rsid="examplersid1",
        name=name,
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )
    return SdrDocument(
        report_suite=rs,
        dimensions=[MagicMock(), MagicMock()],
        metrics=[MagicMock(), MagicMock(), MagicMock()],
        segments=[],
        calculated_metrics=[MagicMock()],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC),
        tool_version="1.19.0",
        fetch_status=fetch_status or {},
        quality=quality,
    )


def test_build_row_properties_required_fields():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc()
    props = build_row_properties(doc, detail_page_id="page-abc")

    assert props["Name"]["title"][0]["text"]["content"] == "Example RS"
    assert props["RSID"]["rich_text"][0]["text"]["content"] == "examplersid1"
    assert props["Last Updated"]["date"]["start"] == "2026-05-16T12:00:00+00:00"
    assert props["Tool Version"]["rich_text"][0]["text"]["content"] == "1.19.0"
    assert props["Dimensions"]["number"] == 2
    assert props["Metrics"]["number"] == 3
    assert props["Segments"]["number"] == 0
    assert props["Calculated Metrics"]["number"] == 1
    assert props["Virtual Report Suites"]["number"] == 0
    assert props["Classifications"]["number"] == 0


def test_build_row_properties_name_falls_back_to_rsid():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc(name="")
    props = build_row_properties(doc, detail_page_id="page-abc")
    assert props["Name"]["title"][0]["text"]["content"] == "examplersid1"


def test_build_row_properties_relation_to_detail_page():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc()
    props = build_row_properties(doc, detail_page_id="page-abc")
    assert props["Page"]["relation"] == [{"id": "page-abc"}]


def test_build_row_properties_optional_fields_present():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc()
    props = build_row_properties(doc, detail_page_id="page-abc")
    assert props["Currency"]["rich_text"][0]["text"]["content"] == "USD"
    assert props["Timezone"]["rich_text"][0]["text"]["content"] == "UTC"
    assert props["Parent RSID"]["rich_text"][0]["text"]["content"] == ""


def test_build_row_properties_quality_verdict_select():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc(quality={"summary": {"verdict": "fail"}})
    props = build_row_properties(doc, detail_page_id="page-abc")
    assert props["Quality Verdict"]["select"] == {"name": "fail"}


def test_build_row_properties_quality_verdict_defaults_to_na():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc(quality=None)
    props = build_row_properties(doc, detail_page_id="page-abc")
    assert props["Quality Verdict"]["select"] == {"name": "n/a"}


def test_build_row_properties_degraded_components_multi_select():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None),
            "classifications": FetchOutcomeMeta(status="partial", expansion_level="minimal"),
            "metrics": FetchOutcomeMeta(status="degraded", expansion_level=None),
        }
    )
    props = build_row_properties(doc, detail_page_id="page-abc")
    names = [o["name"] for o in props["Degraded Components"]["multi_select"]]
    assert names == ["metrics", "virtual_report_suites"]  # sorted, partial excluded
