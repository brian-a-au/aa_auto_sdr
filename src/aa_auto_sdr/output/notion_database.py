"""Notion SDR Registry database — row property builder + upsert.

The registry database (opt-in via ``NOTION_REGISTRY_DATABASE_ID``) sits
alongside the v1.18.0 detail pages: one row per RSID, keyed by the
``RSID`` rich-text property, with a ``Page`` url linking to the
detail page. This module is pure where possible — :func:`build_row_properties`
takes data in and returns Notion property dicts; :func:`upsert_row` performs
the data-source SDK calls (``databases.retrieve`` to resolve the data source,
``data_sources.retrieve`` for its schema, ``data_sources.query``, then
``pages.create`` / ``pages.update``).
"""

from __future__ import annotations

import logging
from typing import Any

from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


REQUIRED_PROPERTIES: tuple[str, ...] = (
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

OPTIONAL_PROPERTIES: tuple[str, ...] = (
    "Page",
    "Currency",
    "Timezone",
    "Parent RSID",
    "Quality Verdict",
    "Degraded Components",
)


class NotionRegistryError(Exception):
    """Raised when the registry database schema is incompatible.

    Caller (NotionWriter / push handler) catches this, logs WARN
    `notion_registry_unavailable`, and continues without aborting the
    detail-page write.
    """


def _rich_text(content: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": content}}]}


def _title(content: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": content}}]}


def _detail_page_url(page_id: str) -> str:
    """Notion URL for a detail page id, used by the registry row's ``Page``
    link property. A ``relation`` cannot be used here: detail pages live under
    a parent page, not as rows in the relation's target database, so Notion
    rejects a relation value pointing at them. A ``url`` property links to the
    page from the registry row without that constraint.
    """
    return f"https://www.notion.so/{page_id.replace('-', '')}"


def build_row_properties(doc: SdrDocument, detail_page_id: str | None) -> dict[str, Any]:
    """Build the full property payload for a database row.

    Caller filters the result against the database's actual property list
    via :func:`filter_payload_to_schema` before sending. ``detail_page_id``
    may be ``None`` if the detail-page write was skipped; the ``Page``
    link is omitted in that case (filter still drops it).
    """
    rs = doc.report_suite
    name = rs.name or rs.rsid
    captured_at_iso = doc.captured_at.isoformat()

    verdict = "n/a"
    if doc.quality is not None:
        summary = doc.quality.get("summary") or {}
        v = summary.get("verdict")
        if isinstance(v, str) and v:
            verdict = v

    degraded_names = sorted(ctype for ctype, meta in doc.fetch_status.items() if meta.status == "degraded")

    props: dict[str, Any] = {
        "Name": _title(name),
        "RSID": _rich_text(rs.rsid),
        "Last Updated": {"date": {"start": captured_at_iso}},
        "Tool Version": _rich_text(doc.tool_version),
        "Dimensions": {"number": len(doc.dimensions)},
        "Metrics": {"number": len(doc.metrics)},
        "Segments": {"number": len(doc.segments)},
        "Calculated Metrics": {"number": len(doc.calculated_metrics)},
        "Virtual Report Suites": {"number": len(doc.virtual_report_suites)},
        "Classifications": {"number": len(doc.classifications)},
        "Currency": _rich_text(rs.currency or ""),
        "Timezone": _rich_text(rs.timezone or ""),
        "Parent RSID": _rich_text(rs.parent_rsid or ""),
        "Quality Verdict": {"select": {"name": verdict}},
        "Degraded Components": {
            "multi_select": [{"name": n} for n in degraded_names],
        },
    }
    if detail_page_id is not None:
        props["Page"] = {"url": _detail_page_url(detail_page_id)}
    return props


def build_row_properties_from_dict(payload: dict, detail_page_id: str | None) -> dict[str, Any]:
    """Same as :func:`build_row_properties` but reads the SDR-JSON or
    snapshot-envelope dict shape directly (push-to-notion path).
    """
    schema = payload.get("schema")
    if isinstance(schema, str) and schema.startswith("aa-sdr-snapshot/"):
        components = payload.get("components") or {}
        rs = components.get("report_suite") or {}
        rsid = payload.get("rsid") or rs.get("rsid") or ""
        captured_at = payload.get("captured_at") or ""
        tool_version = payload.get("tool_version") or ""
        quality = payload.get("quality")
        degraded = list(payload.get("degraded_components") or [])
        counts_src = components
    else:
        rs = payload.get("report_suite") or {}
        rsid = rs.get("rsid") or ""
        captured_at = payload.get("captured_at") or ""
        tool_version = payload.get("tool_version") or ""
        quality = payload.get("quality")
        fetch_status = payload.get("fetch_status") or {}
        degraded = sorted(
            ctype for ctype, meta in fetch_status.items() if isinstance(meta, dict) and meta.get("status") == "degraded"
        )
        counts_src = payload

    if not rsid:
        raise ValueError("payload has no rsid — cannot build registry row")

    name = rs.get("name") or rsid

    verdict = "n/a"
    if isinstance(quality, dict):
        summary = quality.get("summary") or {}
        v = summary.get("verdict")
        if isinstance(v, str) and v:
            verdict = v

    def _count(key: str) -> int:
        items = counts_src.get(key) or []
        return len(items) if isinstance(items, list) else 0

    props: dict[str, Any] = {
        "Name": _title(name),
        "RSID": _rich_text(rsid),
        "Last Updated": {"date": {"start": captured_at}},
        "Tool Version": _rich_text(tool_version),
        "Dimensions": {"number": _count("dimensions")},
        "Metrics": {"number": _count("metrics")},
        "Segments": {"number": _count("segments")},
        "Calculated Metrics": {"number": _count("calculated_metrics")},
        "Virtual Report Suites": {"number": _count("virtual_report_suites")},
        "Classifications": {"number": _count("classifications")},
        "Currency": _rich_text(rs.get("currency") or ""),
        "Timezone": _rich_text(rs.get("timezone") or ""),
        "Parent RSID": _rich_text(rs.get("parent_rsid") or ""),
        "Quality Verdict": {"select": {"name": verdict}},
        "Degraded Components": {
            "multi_select": [{"name": n} for n in sorted(degraded)],
        },
    }
    if detail_page_id is not None:
        props["Page"] = {"url": _detail_page_url(detail_page_id)}
    return props


def filter_payload_to_schema(
    payload: dict[str, Any],
    db_properties: dict[str, Any],
) -> dict[str, Any]:
    """Drop payload keys absent on the database; raise if required keys missing.

    Optional properties absent on the database are silently filtered out
    (logged at DEBUG by the caller via the ``notion_registry_property_missing``
    event). Required properties absent raise :class:`NotionRegistryError`;
    the caller logs ``notion_registry_unavailable`` and continues without
    failing the detail-page write.
    """
    missing_required = [k for k in REQUIRED_PROPERTIES if k not in db_properties]
    if missing_required:
        raise NotionRegistryError(
            f"Notion registry database is missing required properties: {missing_required}. "
            "Run `aa_auto_sdr --notion-print-database-schema` for the canonical list."
        )
    return {k: v for k, v in payload.items() if k in db_properties}


def _resolve_data_source(client: Any, database_id: str) -> tuple[str, dict[str, Any]]:
    """Resolve a database id to ``(data_source_id, properties)``.

    Notion's data-sources API (2025-09) moved a database's schema and rows
    onto one or more data sources. ``databases.retrieve`` returns only the
    ``data_sources`` list, not ``properties``; the schema and the queryable
    rows live on the data source. The registry database is single-source, so
    we resolve the first data source and read the property schema from it.
    """
    db = client.databases.retrieve(database_id=database_id)
    sources = db.get("data_sources") or []
    if not sources:
        raise NotionRegistryError(
            f"Notion database {database_id} has no data sources. "
            "Run `aa_auto_sdr --notion-print-database-schema` for the canonical schema."
        )
    if len(sources) > 1:
        logger.warning(
            "notion_registry_multi_source database_id=%s count=%d (using first)",
            database_id,
            len(sources),
        )
    data_source_id = sources[0]["id"]
    ds = client.data_sources.retrieve(data_source_id=data_source_id)
    db_properties = ds.get("properties") or {}
    return data_source_id, db_properties


def _query_and_upsert(client: Any, data_source_id: str, rsid: str, payload: dict[str, Any]) -> str:
    """Find the row for ``rsid`` in the data source and update it, else create it."""
    response = client.data_sources.query(
        data_source_id=data_source_id,
        filter={"property": "RSID", "rich_text": {"equals": rsid}},
        page_size=2,
    )
    results = response.get("results") or []
    if len(results) > 1:
        logger.warning(
            "notion_registry_duplicate_rows rsid=%s count=%d (updating first)",
            rsid,
            len(results),
        )
    if results:
        row_id = results[0]["id"]
        client.pages.update(page_id=row_id, properties=payload)
        return row_id
    created = client.pages.create(
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties=payload,
    )
    return created["id"]


def upsert_row(
    client: Any,
    *,
    database_id: str,
    rsid: str,
    detail_page_id: str | None,
    doc: SdrDocument,
) -> str:
    """Idempotent upsert by RSID. Returns the database row's page ID.

    Raises :class:`NotionRegistryError` if the database has no data source or
    its data source is missing a required property. SDK errors (401/403/5xx)
    propagate to the caller, which logs ``notion_registry_unavailable``.
    """
    data_source_id, db_properties = _resolve_data_source(client, database_id)
    payload = build_row_properties(doc, detail_page_id)
    payload = filter_payload_to_schema(payload, db_properties)
    return _query_and_upsert(client, data_source_id, rsid, payload)


def upsert_row_from_dict(
    client: Any,
    *,
    database_id: str,
    rsid: str,
    detail_page_id: str | None,
    payload_dict: dict,
) -> str:
    """Same as :func:`upsert_row` but builds from a JSON-shaped dict
    (push-to-notion path).
    """
    data_source_id, db_properties = _resolve_data_source(client, database_id)
    payload = build_row_properties_from_dict(payload_dict, detail_page_id)
    payload = filter_payload_to_schema(payload, db_properties)
    return _query_and_upsert(client, data_source_id, rsid, payload)


_SCHEMA_CHEATSHEET = """\
Notion SDR Registry Database — required schema for aa_auto_sdr v1.19.0
======================================================================

Required properties:
  Name                    title
  RSID                    rich_text
  Last Updated            date
  Tool Version            rich_text
  Dimensions              number
  Metrics                 number
  Segments                number
  Calculated Metrics      number
  Virtual Report Suites   number
  Classifications         number

Optional properties (created when present on the database):
  Page                    url             -> link to the SDR detail page
  Currency                rich_text
  Timezone                rich_text
  Parent RSID             rich_text
  Quality Verdict         select          (suggested options: pass, warn, fail, n/a)
  Degraded Components     multi_select

To enable the registry, set:
  NOTION_REGISTRY_DATABASE_ID=<your-database-id>
"""


def schema_cheatsheet() -> str:
    """Return the canonical schema cheatsheet text printed by
    ``--notion-print-database-schema``.
    """
    return _SCHEMA_CHEATSHEET
