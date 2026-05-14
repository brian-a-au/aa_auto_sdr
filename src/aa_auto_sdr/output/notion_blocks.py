"""Pure block builder for the Notion output writer.

Accepts either an :class:`SdrDocument` or its dict form (``JsonWriter``
output, or a snapshot envelope). No API calls, no I/O — every function
returns Notion block payload dicts ready to send to
``blocks.children.append``.

The dict path exists so ``--push-to-notion`` can publish from JSON
without reconstructing an :class:`SdrDocument` (the project has no
``SdrDocument.from_dict`` today; adding one for one use site would be
premature).
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from aa_auto_sdr.sdr.document import SdrDocument

_NOTION_RICH_TEXT_LIMIT = 2000
_MISSING = "—"

_SECTION_ORDER: list[tuple[str, str, list[str]]] = [
    ("metrics", "📐 Metrics", ["Name", "ID", "Type", "Description"]),
    ("dimensions", "📏 Dimensions", ["Name", "ID", "Type", "Category"]),
    ("segments", "🔖 Segments", ["Name", "ID", "Description"]),
    ("calculated_metrics", "🧮 Calculated Metrics", ["Name", "ID", "Polarity", "Description"]),
    ("virtual_report_suites", "🪞 Virtual Report Suites", ["Name", "ID", "Parent RSID", "Description"]),
    ("classifications", "🔬 Classifications", ["Name", "ID", "RSID"]),
]

_FETCH_STATUS_ICONS = {
    "degraded": "⚠️",
    "partial": "⚠️",
    "failed": "🔴",
    "unavailable": "🔴",
}


def _truncate(text: str) -> str:
    if len(text) <= _NOTION_RICH_TEXT_LIMIT:
        return text
    return text[: _NOTION_RICH_TEXT_LIMIT - 1] + "…"


def _rich_text(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": _truncate(str(content))}}]


def _heading2_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich_text(content)},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _paragraph_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(content)},
    }


def _callout_block(content: str, emoji: str = "📋") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(content),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "default",
        },
    }


def _table_row_block(cells: list[str]) -> dict:
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {"cells": [[{"type": "text", "text": {"content": _truncate(str(c))}}] for c in cells]},
    }


def _table_block(rows: list[list[str]], columns: list[str]) -> dict:
    table_rows = [_table_row_block(columns), *(_table_row_block(row) for row in rows)]
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(columns),
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows,
        },
    }


def _section_blocks(heading: str, columns: list[str], rows: list[list[str]]) -> list[dict]:
    if not rows:
        return []
    return [_heading2_block(heading), _table_block(rows, columns)]


def _val(item: Any, key: str) -> Any:
    """Read a field from an item that is either a dataclass instance or a dict."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _cell(value: Any) -> str:
    if value is None or value == "":
        return _MISSING
    return str(value)


def _rows_for(component_key: str, items: list[Any]) -> list[list[str]]:
    if not items:
        return []
    if component_key == "metrics":
        return [
            [_cell(_val(m, "name")), _cell(_val(m, "id")), _cell(_val(m, "type")), _cell(_val(m, "description"))]
            for m in items
        ]
    if component_key == "dimensions":
        return [
            [_cell(_val(d, "name")), _cell(_val(d, "id")), _cell(_val(d, "type")), _cell(_val(d, "category"))]
            for d in items
        ]
    if component_key == "segments":
        return [[_cell(_val(s, "name")), _cell(_val(s, "id")), _cell(_val(s, "description"))] for s in items]
    if component_key == "calculated_metrics":
        return [
            [_cell(_val(c, "name")), _cell(_val(c, "id")), _cell(_val(c, "polarity")), _cell(_val(c, "description"))]
            for c in items
        ]
    if component_key == "virtual_report_suites":
        return [
            [_cell(_val(v, "name")), _cell(_val(v, "id")), _cell(_val(v, "parent_rsid")), _cell(_val(v, "description"))]
            for v in items
        ]
    if component_key == "classifications":
        return [[_cell(_val(c, "name")), _cell(_val(c, "id")), _cell(_val(c, "rsid"))] for c in items]
    return []


def _metadata_callout(rs: dict[str, Any], captured_at: Any, tool_version: str) -> dict:
    name = rs.get("name") or rs.get("rsid") or _MISSING
    rsid = rs.get("rsid") or _MISSING
    currency = rs.get("currency") or _MISSING
    tz = rs.get("timezone") or _MISSING
    captured_text = str(captured_at) if captured_at else _MISSING
    lines = [
        f"Report Suite: {name} ({rsid})",
        f"Currency: {currency}",
        f"Timezone: {tz}",
        f"Captured at: {captured_text}",
        f"Tool version: {tool_version or _MISSING}",
    ]
    return _callout_block("\n".join(lines))


def _fetch_status_blocks(fetch_status: dict[str, Any]) -> list[dict]:
    if not fetch_status:
        return []
    callouts: list[dict] = []
    for ctype, meta in sorted(fetch_status.items()):
        # meta may be FetchOutcomeMeta or its asdict() form
        status = meta.get("status") if isinstance(meta, dict) else getattr(meta, "status", None)
        if not status or status == "healthy":
            continue
        expansion = meta.get("expansion_level") if isinstance(meta, dict) else getattr(meta, "expansion_level", None)
        emoji = _FETCH_STATUS_ICONS.get(str(status), "⚠️")
        msg = f"{ctype}: {status}"
        if expansion:
            msg += f" (expansion_level={expansion})"
        callouts.append(_callout_block(msg, emoji=emoji))
    if not callouts:
        return []
    return [_heading2_block("🛡️ Data Quality / Fetch Status"), *callouts]


def _normalize_payload(payload: dict) -> dict:
    """Return a normalized SDR-shaped dict (report_suite at top level).

    Accepts a fresh ``SdrDocument.to_dict()`` shape **or** a snapshot
    envelope (``aa-sdr-snapshot/vN``). Raises ``ValueError`` for any
    other shape.
    """
    schema = payload.get("schema")
    if isinstance(schema, str) and schema.startswith("aa-sdr-snapshot/"):
        components = payload.get("components") or {}
        # Envelopes hoist degraded_components (list) and partial_components
        # (dict[ctype, expansion_level]) out of fetch_status; reconstitute so
        # the block builder's fetch-status section renders.
        fetch_status: dict[str, dict] = {
            ctype: {"status": "degraded", "expansion_level": None} for ctype in payload.get("degraded_components") or []
        }
        for ctype, level in (payload.get("partial_components") or {}).items():
            fetch_status[ctype] = {"status": "partial", "expansion_level": level}
        return {
            **components,
            "captured_at": payload.get("captured_at"),
            "tool_version": payload.get("tool_version"),
            "quality": payload.get("quality"),
            "fetch_status": fetch_status,
        }
    if "report_suite" in payload and "captured_at" in payload:
        return payload
    raise ValueError(f"Unrecognized Notion push payload shape; top-level keys: {sorted(payload.keys())}")


def _tool_version_footer(tool_version: str) -> dict:
    return _paragraph_block(f"Generated by aa_auto_sdr v{tool_version or _MISSING}")


def _blocks_from_normalized(d: dict) -> list[dict]:
    rs_raw = d.get("report_suite") or {}
    rs = rs_raw if isinstance(rs_raw, dict) else (asdict(rs_raw) if is_dataclass(rs_raw) else {})

    captured_at = d.get("captured_at")
    tool_version = d.get("tool_version") or ""
    fetch_status = d.get("fetch_status") or {}

    blocks: list[dict] = [_metadata_callout(rs, captured_at, tool_version), _divider_block()]
    blocks.extend(_fetch_status_blocks(fetch_status))
    for key, heading, columns in _SECTION_ORDER:
        items = d.get(key) or []
        rows = _rows_for(key, items)
        blocks.extend(_section_blocks(heading, columns, rows))
    blocks.append(_divider_block())
    blocks.append(_tool_version_footer(tool_version))
    return blocks


def build_blocks_from_document(doc: SdrDocument) -> list[dict]:
    """Build Notion blocks from an :class:`SdrDocument`.

    The block builder is pure — it does not read environment variables,
    does not import ``notion_client``, and does no I/O.
    """
    d = doc.to_dict()
    return _blocks_from_normalized(d)


def build_blocks_from_dict(payload: dict) -> list[dict]:
    """Build Notion blocks from a dict payload.

    Accepts a fresh SDR JSON output **or** a snapshot envelope; the
    envelope shape is unwrapped via :func:`_normalize_payload`.
    """
    return _blocks_from_normalized(_normalize_payload(payload))
