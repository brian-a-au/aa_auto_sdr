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
from dataclasses import dataclass, field
from typing import Any

from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)

# Module-level cache: database_id → (data_source_id, db_properties).
# Populated lazily by _resolve_data_source; cleared between tests (and on
# explicit refresh) via clear_data_source_cache().
_DATA_SOURCE_CACHE: dict[str, tuple[str, dict]] = {}


def clear_data_source_cache() -> None:
    """Empty the data-source resolution cache.

    Call this when you want to force a fresh ``databases.retrieve`` /
    ``data_sources.retrieve`` round-trip on the next upsert — for example,
    after a schema repair or in test teardown.
    """
    _DATA_SOURCE_CACHE.clear()


# Single source of truth for the registry database schema. The upsert payload,
# the repair command (--notion-repair-database), and the cheatsheet
# (--notion-print-database-schema) all derive from this table.
PROPERTY_SCHEMA: dict[str, dict] = {
    "Name": {"type": "title", "required": True, "definition": {"title": {}}},
    "RSID": {"type": "rich_text", "required": True, "definition": {"rich_text": {}}},
    "Last Updated": {"type": "date", "required": True, "definition": {"date": {}}},
    "Tool Version": {"type": "rich_text", "required": True, "definition": {"rich_text": {}}},
    "Dimensions": {"type": "number", "required": True, "definition": {"number": {}}},
    "Metrics": {"type": "number", "required": True, "definition": {"number": {}}},
    "Segments": {"type": "number", "required": True, "definition": {"number": {}}},
    "Calculated Metrics": {"type": "number", "required": True, "definition": {"number": {}}},
    "Virtual Report Suites": {"type": "number", "required": True, "definition": {"number": {}}},
    "Classifications": {"type": "number", "required": True, "definition": {"number": {}}},
    "Page": {"type": "url", "required": False, "definition": {"url": {}}, "hint": "-> link to the SDR detail page"},
    "Company": {"type": "rich_text", "required": False, "definition": {"rich_text": {}}},
    "Currency": {"type": "rich_text", "required": False, "definition": {"rich_text": {}}},
    "Timezone": {"type": "rich_text", "required": False, "definition": {"rich_text": {}}},
    "Parent RSID": {"type": "rich_text", "required": False, "definition": {"rich_text": {}}},
    "Quality Verdict": {
        "type": "select",
        "required": False,
        "definition": {"select": {}},
        "hint": "(suggested options: pass, warn, fail, n/a)",
    },
    "Degraded Components": {"type": "multi_select", "required": False, "definition": {"multi_select": {}}},
}

REQUIRED_PROPERTIES: tuple[str, ...] = tuple(n for n, s in PROPERTY_SCHEMA.items() if s["required"])
OPTIONAL_PROPERTIES: tuple[str, ...] = tuple(n for n, s in PROPERTY_SCHEMA.items() if not s["required"])


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


def build_row_properties(doc: SdrDocument, detail_page_id: str | None, company: str = "") -> dict[str, Any]:
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
    if company:
        props["Company"] = _rich_text(company)
    if detail_page_id is not None:
        props["Page"] = {"url": _detail_page_url(detail_page_id)}
    return props


def build_row_properties_from_dict(payload: dict, detail_page_id: str | None, company: str = "") -> dict[str, Any]:
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
    if company:
        props["Company"] = _rich_text(company)
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
    dropped = [k for k in payload if k not in db_properties]
    for name in dropped:
        logger.debug("notion_registry_property_missing name=%s", name)
    return {k: v for k, v in payload.items() if k in db_properties}


def _resolve_data_source(client: Any, database_id: str) -> tuple[str, dict[str, Any]]:
    """Resolve a database id to ``(data_source_id, properties)``.

    Notion's data-sources API (2025-09) moved a database's schema and rows
    onto one or more data sources. ``databases.retrieve`` returns only the
    ``data_sources`` list, not ``properties``; the schema and the queryable
    rows live on the data source. The registry database is single-source, so
    we resolve the first data source and read the property schema from it.

    Results are cached in :data:`_DATA_SOURCE_CACHE` (keyed by ``database_id``)
    so that batch and watch runs resolve each database only once. Call
    :func:`clear_data_source_cache` to force a fresh round-trip.
    """
    if database_id in _DATA_SOURCE_CACHE:
        return _DATA_SOURCE_CACHE[database_id]

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
    result: tuple[str, dict[str, Any]] = (data_source_id, db_properties)
    _DATA_SOURCE_CACHE[database_id] = result
    return result


def _query_and_upsert(client: Any, data_source_id: str, rsid: str, payload: dict[str, Any], company: str = "") -> str:
    """Find the row for ``rsid`` (and ``company`` when present) and update it, else create it."""
    if company and "Company" in payload:
        flt = {
            "and": [
                {"property": "RSID", "rich_text": {"equals": rsid}},
                {"property": "Company", "rich_text": {"equals": company}},
            ]
        }
    else:
        flt = {"property": "RSID", "rich_text": {"equals": rsid}}
    response = client.data_sources.query(data_source_id=data_source_id, filter=flt, page_size=2)
    results = response.get("results") or []
    if len(results) > 1:
        logger.warning("notion_registry_duplicate_rows rsid=%s count=%d (updating first)", rsid, len(results))
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
    company: str = "",
) -> str:
    """Idempotent upsert by RSID (and Company when provided). Returns the database row's page ID.

    Raises :class:`NotionRegistryError` if the database has no data source or
    its data source is missing a required property. SDK errors (401/403/5xx)
    propagate to the caller, which logs ``notion_registry_unavailable``.
    """
    data_source_id, db_properties = _resolve_data_source(client, database_id)
    payload = build_row_properties(doc, detail_page_id, company=company)
    payload = filter_payload_to_schema(payload, db_properties)
    return _query_and_upsert(client, data_source_id, rsid, payload, company=company)


def upsert_row_from_dict(
    client: Any,
    *,
    database_id: str,
    rsid: str,
    detail_page_id: str | None,
    payload_dict: dict,
    company: str = "",
) -> str:
    """Same as :func:`upsert_row` but builds from a JSON-shaped dict
    (push-to-notion path).
    """
    data_source_id, db_properties = _resolve_data_source(client, database_id)
    payload = build_row_properties_from_dict(payload_dict, detail_page_id, company=company)
    payload = filter_payload_to_schema(payload, db_properties)
    return _query_and_upsert(client, data_source_id, rsid, payload, company=company)


@dataclass
class RepairResult:
    """Result of :func:`repair_database`.

    ``to_add`` — property names that were missing and will be (or were) added.
    ``conflicts`` — ``(name, want_type, have_type)`` tuples for properties that
        exist on the database but have the wrong type; these are skipped.
    ``applied`` — ``True`` if the update was actually sent (``dry_run=False``
        and at least one property was missing).
    """

    to_add: list[str] = field(default_factory=list)
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)
    applied: bool = False


def repair_database(
    client: Any,
    *,
    database_id: str,
    dry_run: bool = True,
) -> RepairResult:
    """Repair a Notion registry database to match :data:`PROPERTY_SCHEMA`.

    Compares the database's current property set against the canonical
    ``PROPERTY_SCHEMA``.  Missing properties are collected into ``to_add``
    and — when ``dry_run=False`` — added via a single ``data_sources.update``
    call.  Properties present but with the wrong type are recorded as
    ``conflicts`` and never touched.

    Returns a :class:`RepairResult` describing what was (or would be) changed.
    Raises :class:`NotionRegistryError` if the database has no data source.
    """
    data_source_id, db_properties = _resolve_data_source(client, database_id)

    to_add: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    payload: dict[str, Any] = {}

    for name, schema_entry in PROPERTY_SCHEMA.items():
        if name not in db_properties:
            to_add.append(name)
            payload[name] = schema_entry["definition"]
        elif db_properties[name].get("type") != schema_entry["type"]:
            conflicts.append((name, schema_entry["type"], db_properties[name].get("type", "unknown")))

    applied = False
    if to_add and not dry_run:
        client.data_sources.update(data_source_id=data_source_id, properties=payload)
        applied = True

    return RepairResult(to_add=to_add, conflicts=conflicts, applied=applied)


def build_create_properties() -> dict[str, Any]:
    """Property-definition map for ``databases.create`` ``initial_data_source``.

    Every :data:`PROPERTY_SCHEMA` entry keyed by name, value = its ``definition``
    (e.g. ``{"title": {}}``, ``{"rich_text": {}}``). Includes the single required
    ``title`` property (``Name``). This is the same definition shape
    :func:`repair_database` sends to ``data_sources.update``, so a database
    created from this map needs zero repair.
    """
    return {name: entry["definition"] for name, entry in PROPERTY_SCHEMA.items()}


def create_database(client: Any, *, parent_page_id: str, title: str) -> tuple[str, str]:
    """Create the registry database under ``parent_page_id`` with the full schema.

    Issues a single ``databases.create`` call (2025-09 data-source model:
    property definitions live under ``initial_data_source.properties``).
    Returns ``(database_id, database_url)``. SDK errors propagate to the caller.
    """
    created = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": title}}],
        initial_data_source={"properties": build_create_properties()},
    )
    database_id = created["id"]
    database_url = created.get("url") or f"https://www.notion.so/{database_id.replace('-', '')}"
    return database_id, database_url


def schema_cheatsheet() -> str:
    """Return the canonical schema cheatsheet printed by
    ``--notion-print-database-schema``, derived from PROPERTY_SCHEMA.
    """

    def _entry(name: str) -> str:
        entry = PROPERTY_SCHEMA[name]
        line = f"  {name:<23} {entry['type']}"
        hint = entry.get("hint")
        if hint:
            line = f"{line} {hint}"
        return line

    req = "\n".join(_entry(name) for name in REQUIRED_PROPERTIES)
    opt = "\n".join(_entry(name) for name in OPTIONAL_PROPERTIES)
    return (
        "Notion SDR Registry Database — required schema for aa_auto_sdr\n"
        "==============================================================\n\n"
        "Required properties:\n"
        f"{req}\n\n"
        "Optional properties (created when present on the database):\n"
        f"{opt}\n\n"
        "Company enables multi-company databases: when set, rows are keyed by\n"
        "(Company, RSID) instead of RSID alone.\n\n"
        "To enable the registry, set:\n"
        "  NOTION_REGISTRY_DATABASE_ID=<your-database-id>\n"
    )
