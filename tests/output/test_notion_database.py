"""Tests for the Notion SDR Registry database row builder + upsert."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.output import notion_database as db
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument


def test_company_is_optional_property():
    assert "Company" in db.PROPERTY_SCHEMA
    assert db.PROPERTY_SCHEMA["Company"]["required"] is False
    assert db.PROPERTY_SCHEMA["Company"]["type"] == "rich_text"
    assert "Company" in db.OPTIONAL_PROPERTIES
    assert "Company" not in db.REQUIRED_PROPERTIES


def test_required_optional_derived_from_schema():
    derived_required = tuple(n for n, s in db.PROPERTY_SCHEMA.items() if s["required"])
    derived_optional = tuple(n for n, s in db.PROPERTY_SCHEMA.items() if not s["required"])
    assert derived_required == db.REQUIRED_PROPERTIES
    assert derived_optional == db.OPTIONAL_PROPERTIES


def test_cheatsheet_mentions_company():
    text = db.schema_cheatsheet()
    assert "Company" in text
    assert "RSID" in text


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


def test_build_row_properties_links_to_detail_page():
    from aa_auto_sdr.output.notion_database import build_row_properties

    doc = _make_doc()
    props = build_row_properties(doc, detail_page_id="page-abc")
    # Page is a url property, not a relation: detail pages live under a parent
    # page, not as rows in the relation's target database, so a relation value
    # would be rejected by Notion. See notion_database._detail_page_url.
    assert props["Page"]["url"] == "https://www.notion.so/pageabc"


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
    client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1", "name": "ds"}]}
    client.data_sources.retrieve.return_value = {
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
    client.data_sources.query.return_value = {"results": []}
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
    assert call_kwargs["parent"] == {"type": "data_source_id", "data_source_id": "ds-1"}
    assert "RSID" in call_kwargs["properties"]


def test_upsert_row_updates_existing_match():
    from aa_auto_sdr.output.notion_database import upsert_row

    client = MagicMock()
    client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1", "name": "ds"}]}
    client.data_sources.retrieve.return_value = {
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
    client.data_sources.query.return_value = {"results": [{"id": "existing-row"}]}

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
    client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1", "name": "ds"}]}
    client.data_sources.retrieve.return_value = {
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
    client.data_sources.query.return_value = {"results": [{"id": "first"}, {"id": "second"}]}

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
    client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1", "name": "ds"}]}
    client.data_sources.retrieve.return_value = {
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
    client.data_sources.query.return_value = {"results": []}
    client.pages.create.return_value = {"id": "new-row"}

    upsert_row(
        client,
        database_id="db-id",
        rsid="examplersid1",
        detail_page_id="page-abc",
        doc=_make_doc(),
    )

    query_call = client.data_sources.query.call_args
    assert query_call.kwargs["data_source_id"] == "ds-1"
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


# --- build_row_properties_from_dict: envelope + SDR-JSON edge paths ---


def test_build_row_properties_from_dict_snapshot_envelope():
    from aa_auto_sdr.output.notion_database import build_row_properties_from_dict

    payload = {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "rs1",
        "captured_at": "2026-05-16T12:00:00+00:00",
        "tool_version": "1.19.0",
        "degraded_components": ["segments", "metrics"],
        "partial_components": {},
        "quality": {"summary": {"verdict": "warn"}},
        "components": {
            "report_suite": {
                "rsid": "rs1",
                "name": "RS One",
                "currency": "EUR",
                "timezone": "UTC",
                "parent_rsid": "parent1",
            },
            "dimensions": [{}, {}, {}],
            "metrics": [{}],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }
    props = build_row_properties_from_dict(payload, detail_page_id="page-1")
    assert props["RSID"]["rich_text"][0]["text"]["content"] == "rs1"
    assert props["Name"]["title"][0]["text"]["content"] == "RS One"
    assert props["Dimensions"]["number"] == 3
    assert props["Metrics"]["number"] == 1
    assert props["Currency"]["rich_text"][0]["text"]["content"] == "EUR"
    assert props["Parent RSID"]["rich_text"][0]["text"]["content"] == "parent1"
    assert props["Quality Verdict"]["select"] == {"name": "warn"}
    assert [o["name"] for o in props["Degraded Components"]["multi_select"]] == ["metrics", "segments"]
    assert props["Page"]["url"] == "https://www.notion.so/page1"  # dashes stripped


def test_build_row_properties_from_dict_sdr_json_quality_and_degraded():
    from aa_auto_sdr.output.notion_database import build_row_properties_from_dict

    payload = {
        "report_suite": {"rsid": "rs2", "name": "RS Two", "currency": "USD", "timezone": "UTC", "parent_rsid": None},
        "captured_at": "2026-05-16T12:00:00+00:00",
        "tool_version": "1.19.0",
        "dimensions": [{}],
        "metrics": [],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
        "fetch_status": {"segments": {"status": "degraded"}, "metrics": {"status": "partial"}},
        "quality": {"summary": {"verdict": "fail"}},
    }
    props = build_row_properties_from_dict(payload, detail_page_id=None)
    assert props["Quality Verdict"]["select"] == {"name": "fail"}
    # only the degraded component, not the partial one
    assert [o["name"] for o in props["Degraded Components"]["multi_select"]] == ["segments"]
    assert "Page" not in props  # detail_page_id is None


def test_build_row_properties_from_dict_raises_without_rsid():
    from aa_auto_sdr.output.notion_database import build_row_properties_from_dict

    with pytest.raises(ValueError, match="rsid"):
        build_row_properties_from_dict({"report_suite": {}, "captured_at": "x"}, detail_page_id=None)


# --- _resolve_data_source edge paths ---


def test_resolve_data_source_raises_when_no_sources():
    from aa_auto_sdr.output.notion_database import NotionRegistryError, _resolve_data_source

    client = MagicMock()
    client.databases.retrieve.return_value = {"data_sources": []}
    with pytest.raises(NotionRegistryError, match="no data sources"):
        _resolve_data_source(client, "db-id")


def test_resolve_data_source_warns_on_multiple(caplog):
    import logging

    from aa_auto_sdr.output.notion_database import _resolve_data_source

    client = MagicMock()
    client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1"}, {"id": "ds-2"}]}
    client.data_sources.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
    with caplog.at_level(logging.WARNING, logger="aa_auto_sdr.output.notion_database"):
        data_source_id, db_properties = _resolve_data_source(client, "db-id")
    assert data_source_id == "ds-1"  # first source wins
    assert "Name" in db_properties
    assert any("notion_registry_multi_source" in r.message for r in caplog.records)


def test_filter_logs_dropped_optional(caplog):
    import logging

    payload = {
        "Name": {},
        "RSID": {},
        "Last Updated": {},
        "Tool Version": {},
        "Dimensions": {},
        "Metrics": {},
        "Segments": {},
        "Calculated Metrics": {},
        "Virtual Report Suites": {},
        "Classifications": {},
        "Company": {},
    }
    db_props = {k: {} for k in db.REQUIRED_PROPERTIES}  # Company absent on DB
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.output.notion_database"):
        out = db.filter_payload_to_schema(payload, db_props)
    assert "Company" not in out
    assert any("notion_registry_property_missing" in r.message and "Company" in r.message for r in caplog.records)


# --- company-aware _query_and_upsert filter tests ---


class _FakeClient:
    def __init__(self, existing_rows=None, db_props=None):
        self.queries = []
        self.created = []
        self.updated = []
        self._rows = existing_rows or []
        self._db_props = db_props if db_props is not None else {k: {} for k in db.PROPERTY_SCHEMA}

        outer = self

        class _DS:
            def query(self, **kw):
                outer.queries.append(kw)
                return {"results": outer._rows}

            def retrieve(self, **kw):
                return {"properties": outer._db_props}

        class _DBs:
            def retrieve(self, **kw):
                return {"data_sources": [{"id": "ds1"}]}

        class _Pages:
            def create(self, **kw):
                outer.created.append(kw)
                return {"id": "new_row"}

            def update(self, **kw):
                outer.updated.append(kw)

        self.data_sources = _DS()
        self.databases = _DBs()
        self.pages = _Pages()


def test_query_filter_uses_company_when_present():
    client = _FakeClient()
    db._query_and_upsert(client, "ds1", "rs1", {"RSID": {}, "Company": {}}, company="acme")
    flt = client.queries[0]["filter"]
    assert "and" in flt
    props = {clause["property"] for clause in flt["and"]}
    assert props == {"RSID", "Company"}


def test_query_filter_rsid_only_without_company():
    client = _FakeClient()
    db._query_and_upsert(client, "ds1", "rs1", {"RSID": {}}, company="")
    flt = client.queries[0]["filter"]
    assert flt == {"property": "RSID", "rich_text": {"equals": "rs1"}}


def test_query_filter_rsid_only_when_company_set_but_not_in_payload():
    """Backward-compat: company is non-empty but the payload does NOT contain
    a 'Company' key (the database lacks the Company column so filter_payload_to_schema
    dropped it). The filter must fall back to the RSID-only form, not an AND filter.
    """
    client = _FakeClient()
    # Payload has no "Company" key — simulates a database that lacks the column
    db._query_and_upsert(client, "ds1", "rs1", {"RSID": {}}, company="acme")
    flt = client.queries[0]["filter"]
    assert flt == {"property": "RSID", "rich_text": {"equals": "rs1"}}


# --- repair_database tests ---


class _RepairClient:
    """Fake client for repair_database tests; spies on data_sources.update."""

    def __init__(self, existing_props: dict | None = None):
        self.update_calls: list[dict] = []
        # Properties already on the DB — defaults to all PROPERTY_SCHEMA entries with correct types
        if existing_props is None:
            existing_props = {name: {"type": schema["type"]} for name, schema in db.PROPERTY_SCHEMA.items()}
        self._existing_props = existing_props

        outer = self

        class _DS:
            def retrieve(self, **kw):
                return {"properties": outer._existing_props}

            def update(self, data_source_id=None, **kw):
                outer.update_calls.append({"data_source_id": data_source_id, **kw})

        class _DBs:
            def retrieve(self, **kw):
                return {"data_sources": [{"id": "ds-repair"}]}

        self.data_sources = _DS()
        self.databases = _DBs()


def test_repair_all_missing():
    """All PROPERTY_SCHEMA entries absent → to_add = all names, conflicts = [], applied = False."""
    from aa_auto_sdr.output.notion_database import repair_database

    client = _RepairClient(existing_props={})
    result = repair_database(client, database_id="db-id")  # dry_run=True by default

    assert set(result.to_add) == set(db.PROPERTY_SCHEMA.keys())
    assert result.conflicts == []
    assert result.applied is False
    assert client.update_calls == []  # dry run — no update sent


def test_repair_nothing_to_add():
    """All properties present with correct types → to_add = [], conflicts = []."""
    from aa_auto_sdr.output.notion_database import repair_database

    # Default _RepairClient has all properties with correct types
    client = _RepairClient()
    result = repair_database(client, database_id="db-id")

    assert result.to_add == []
    assert result.conflicts == []
    assert result.applied is False


def test_repair_type_conflict():
    """One property present with wrong type → appears in conflicts, NOT in to_add."""
    from aa_auto_sdr.output.notion_database import repair_database

    # RSID should be rich_text but we give it number
    correct_props = {name: {"type": schema["type"]} for name, schema in db.PROPERTY_SCHEMA.items()}
    correct_props["RSID"] = {"type": "number"}  # type mismatch
    client = _RepairClient(existing_props=correct_props)

    result = repair_database(client, database_id="db-id")

    assert "RSID" not in result.to_add
    conflict_names = [c[0] for c in result.conflicts]
    assert "RSID" in conflict_names
    # Check the tuple shape: (name, want_type, have_type)
    rsid_conflict = next(c for c in result.conflicts if c[0] == "RSID")
    assert rsid_conflict == ("RSID", "rich_text", "number")


def test_repair_apply_calls_update():
    """dry_run=False with at least one missing property → data_sources.update called once; applied = True."""
    from aa_auto_sdr.output.notion_database import PROPERTY_SCHEMA, repair_database

    # Remove one property from the DB
    existing = {name: {"type": schema["type"]} for name, schema in PROPERTY_SCHEMA.items()}
    del existing["Company"]  # Company is missing
    client = _RepairClient(existing_props=existing)

    result = repair_database(client, database_id="db-id", dry_run=False)

    assert "Company" in result.to_add
    assert result.applied is True
    assert len(client.update_calls) == 1
    # The update payload should contain Company's definition
    call_props = client.update_calls[0]["properties"]
    assert "Company" in call_props


def test_repair_dry_run_no_update():
    """dry_run=True with missing properties → data_sources.update NOT called; applied = False."""
    from aa_auto_sdr.output.notion_database import PROPERTY_SCHEMA, repair_database

    existing = {name: {"type": schema["type"]} for name, schema in PROPERTY_SCHEMA.items()}
    del existing["Timezone"]  # Timezone is missing
    client = _RepairClient(existing_props=existing)

    result = repair_database(client, database_id="db-id", dry_run=True)

    assert "Timezone" in result.to_add
    assert result.applied is False
    assert client.update_calls == []
