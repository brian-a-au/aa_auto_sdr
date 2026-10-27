"""Shared helpers for output writers.

stringify_cell() coerces arbitrary Python values into a single string suitable
for tabular output (csv, excel, html, markdown). escape_pipe() and escape_html()
escape format-specific characters in cell content."""

from __future__ import annotations

import html as _html
import json
from typing import Any


def stringify_cell(value: Any) -> str:
    """Coerce a value to a string for tabular display.

    - None         -> ""
    - bool         -> "true" / "false"
    - dict / list  -> compact JSON (keys sorted in dicts for stable diffs)
    - everything else -> str(value)
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(", ", ": "))
    return str(value)


# Leading characters Excel interprets as the start of a formula (or, for
# tab/CR, as cell-splitting control characters) when importing a CSV.
# Per OWASP CSV-injection guidance.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def neutralize_formula(text: str) -> str:
    """Defuse spreadsheet formula injection for CSV cells.

    Component names are authored by arbitrary org users; a name like
    `=HYPERLINK(...)` must not execute when the CSV is opened in Excel.
    Prefixing a single quote is the OWASP-recommended neutralization — Excel
    treats the cell as text. Applied only to cells that would otherwise be
    interpreted as formulas, so ordinary values round-trip unchanged."""
    if text.startswith(_FORMULA_TRIGGERS):
        return "'" + text
    return text


def escape_pipe(text: str) -> str:
    """Escape Markdown-table-breaking characters in a cell value.

    Pipes become \\|. Newlines become <br> (GFM-supported)."""
    return text.replace("|", r"\|").replace("\n", "<br>")


def escape_html(text: str) -> str:
    """Escape HTML special characters. Wraps stdlib html.escape."""
    return _html.escape(text, quote=True)


def render_provenance_pairs(doc: Any) -> list[tuple[str, str]]:
    """Summary rows for a document rebuilt by `--render-from`; empty for a live capture."""
    rendered = getattr(doc, "rendered", None)
    if rendered is None:
        return []
    return [
        ("Rendered at", rendered.rendered_at.isoformat()),
        ("Rendered by tool version", rendered.tool_version),
    ]


def render_provenance_line(doc: Any) -> str | None:
    """One sentence naming the render step and the original capture, or None for a live capture."""
    rendered = getattr(doc, "rendered", None)
    if rendered is None:
        return None
    return (
        f"Rendered at {rendered.rendered_at.isoformat()} by tool version {rendered.tool_version} "
        f"from a capture taken at {doc.captured_at.isoformat()} by tool version {doc.tool_version}."
    )
