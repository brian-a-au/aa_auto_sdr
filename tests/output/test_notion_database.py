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


def test_filter_payload_to_schema_drops_absent_optional():
    from aa_auto_sdr.output.notion_database import (
        build_row_properties,
        filter_payload_to_schema,
    )

    doc = _make_doc()
    payload = build_row_properties(doc, detail_page_id="page-abc")
    db_properties = {
        # required only — no Page, no Currency, no Timezone, etc.
        "Name": {"type": "title"},
        "RSID": {"type": "rich_text"},
        "Last Updated": {"type": "date"},
        "Tool Version": {"type": "rich_text"},
        "Dimensions": {"type": "number"},
        "Metrics": {"type": "number"},
        "Segments": {"type": "number"},
        "Calculated Metrics": {"type": "number"},
        "Virtual Report Suites": {"type": "number"},
        "Classifications": {"type": "number"},
    }
    filtered = filter_payload_to_schema(payload, db_properties)
    assert set(filtered) == set(db_properties)


def test_filter_payload_to_schema_raises_when_required_missing():
    from aa_auto_sdr.output.notion_database import (
        NotionRegistryError,
        build_row_properties,
        filter_payload_to_schema,
    )

    doc = _make_doc()
    payload = build_row_properties(doc, detail_page_id="page-abc")
    db_properties_missing_rsid = {
        "Name": {"type": "title"},
        # RSID absent
        "Last Updated": {"type": "date"},
        "Tool Version": {"type": "rich_text"},
        "Dimensions": {"type": "number"},
        "Metrics": {"type": "number"},
        "Segments": {"type": "number"},
        "Calculated Metrics": {"type": "number"},
        "Virtual Report Suites": {"type": "number"},
        "Classifications": {"type": "number"},
    }
    with pytest.raises(NotionRegistryError, match="RSID"):
        filter_payload_to_schema(payload, db_properties_missing_rsid)


def test_upsert_row_creates_when_no_match():
    from aa_auto_sdr.output.notion_database import upsert_row

    client = MagicMock()
    client.databases.retrieve.return_value = {
        "properties": {
            p: {"type": "x"}
            for p in (
                "Name",
                "RSID",
                "Last Updated",
                "Tool Version",
                "Dimensions",
                "Metrics",
                "Segments",
                "Calculated Metrics",
                "Virtual Report Suites",
                "Classifications",
                "Page",
            )
        },
    }
    client.databases.query.return_value = {"results": []}
    client.pages.create.return_value = {"id": "new-row-id"}

    row_id = upsert_row(
        client,
        database_id="db-id",
        rsid="examplersid1",
        detail_page_id="page-abc",
        doc=_make_doc(),
    )

    assert row_id == "new-row-id"
    client.pages.create.assert_called_once()
    client.pages.update.assert_not_called()
    call_kwargs = client.pages.create.call_args.kwargs
    assert call_kwargs["parent"] == {"database_id": "db-id"}
    assert "RSID" in call_kwargs["properties"]


def test_upsert_row_updates_existing_match():
    from aa_auto_sdr.output.notion_database import upsert_row

    client = MagicMock()
    client.databases.retrieve.return_value = {
        "properties": {
            p: {"type": "x"}
            for p in (
                "Name",
                "RSID",
                "Last Updated",
                "Tool Version",
                "Dimensions",
                "Metrics",
                "Segments",
                "Calculated Metrics",
                "Virtual Report Suites",
                "Classifications",
            )
        },
    }
    client.databases.query.return_value = {"results": [{"id": "existing-row"}]}

    row_id = upsert_row(
        client,
        database_id="db-id",
        rsid="examplersid1",
        detail_page_id="page-abc",
        doc=_make_doc(),
    )

    assert row_id == "existing-row"
    client.pages.update.assert_called_once_with(
        page_id="existing-row",
        properties=client.pages.update.call_args.kwargs["properties"],
    )
    client.pages.create.assert_not_called()


def test_upsert_row_duplicate_match_logs_warn_and_picks_first(caplog):
    import logging

    from aa_auto_sdr.output.notion_database import upsert_row

    client = MagicMock()
    client.databases.retrieve.return_value = {
        "properties": {
            p: {"type": "x"}
            for p in (
                "Name",
                "RSID",
                "Last Updated",
                "Tool Version",
                "Dimensions",
                "Metrics",
                "Segments",
                "Calculated Metrics",
                "Virtual Report Suites",
                "Classifications",
            )
        },
    }
    client.databases.query.return_value = {"results": [{"id": "first"}, {"id": "second"}]}

    with caplog.at_level(logging.WARNING, logger="aa_auto_sdr.output.notion_database"):
        row_id = upsert_row(
            client,
            database_id="db-id",
            rsid="examplersid1",
            detail_page_id="page-abc",
            doc=_make_doc(),
        )

    assert row_id == "first"
    assert any("notion_registry_duplicate_rows" in r.message for r in caplog.records)


def test_upsert_row_query_filter_uses_rsid_property():
    from aa_auto_sdr.output.notion_database import upsert_row

    client = MagicMock()
    client.databases.retrieve.return_value = {
        "properties": {
            p: {"type": "x"}
            for p in (
                "Name",
                "RSID",
                "Last Updated",
                "Tool Version",
                "Dimensions",
                "Metrics",
                "Segments",
                "Calculated Metrics",
                "Virtual Report Suites",
                "Classifications",
            )
        },
    }
    client.databases.query.return_value = {"results": []}
    client.pages.create.return_value = {"id": "new-row"}

    upsert_row(
        client,
        database_id="db-id",
        rsid="examplersid1",
        detail_page_id="page-abc",
        doc=_make_doc(),
    )

    query_call = client.databases.query.call_args
    assert query_call.kwargs["database_id"] == "db-id"
    assert query_call.kwargs["filter"] == {
        "property": "RSID",
        "rich_text": {"equals": "examplersid1"},
    }


def test_schema_cheatsheet_lists_all_required_properties():
    from aa_auto_sdr.output.notion_database import REQUIRED_PROPERTIES, schema_cheatsheet

    text = schema_cheatsheet()
    for prop in REQUIRED_PROPERTIES:
        assert prop in text


def test_schema_cheatsheet_mentions_env_var_name():
    from aa_auto_sdr.output.notion_database import schema_cheatsheet

    assert "NOTION_REGISTRY_DATABASE_ID" in schema_cheatsheet()
