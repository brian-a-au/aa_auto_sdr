"""Notion SDR Registry database — row property builder + upsert.

The registry database (opt-in via ``NOTION_REGISTRY_DATABASE_ID``) sits
alongside the v1.18.0 detail pages: one row per RSID, keyed by the
``RSID`` rich-text property, with a ``Page`` relation pointing at the
detail page. This module is pure where possible — :func:`build_row_properties`
takes data in and returns Notion property dicts; :func:`upsert_row` performs
the three SDK calls (``databases.retrieve``, ``databases.query``, then
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


def build_row_properties(doc: SdrDocument, detail_page_id: str | None) -> dict[str, Any]:
    """Build the full property payload for a database row.

    Caller filters the result against the database's actual property list
    via :func:`filter_payload_to_schema` before sending. ``detail_page_id``
    may be ``None`` if the detail-page write was skipped; the ``Page``
    relation is omitted in that case (filter still drops it).
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

    degraded_names = sorted(
        ctype for ctype, meta in doc.fetch_status.items() if meta.status == "degraded"
    )

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
        props["Page"] = {"relation": [{"id": detail_page_id}]}
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
            ctype
            for ctype, meta in fetch_status.items()
            if isinstance(meta, dict) and meta.get("status") == "degraded"
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
        props["Page"] = {"relation": [{"id": detail_page_id}]}
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
