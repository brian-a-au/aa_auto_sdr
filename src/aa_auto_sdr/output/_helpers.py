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


def component_headers(family: str, cls: type) -> list[str]:
    """Column names for one component family: the model fields, then the
    derived definition columns (summary and references) when the family has them."""
    from dataclasses import fields

    from aa_auto_sdr.sdr.definitions import DERIVED_COLUMNS

    return [f.name for f in fields(cls)] + list(DERIVED_COLUMNS.get(family, ()))


def component_values(family: str, item: Any) -> list[Any]:
    """Cell values for one component, in `component_headers` order.

    Model fields are returned as-is (each writer stringifies them). Derived
    reference lists are joined with ", " so tabular formats show plain IDs."""
    from dataclasses import fields

    from aa_auto_sdr.sdr.definitions import derived_fields

    values: list[Any] = [getattr(item, f.name) for f in fields(item)]
    values.extend(", ".join(v) if isinstance(v, list) else v for v in derived_fields(family, item).values())
    return values


# Human labels for the references appendix in Excel, Markdown, and HTML.
REFERENCE_HEADINGS: tuple[str, ...] = (
    "Family",
    "ID",
    "Name",
    "Relation",
    "Kind",
    "Target Family",
    "Target ID",
    "Target Name",
    "Status",
)

_FAMILY_LABELS = {
    "calculated_metrics": "Calculated Metrics",
    "metrics": "Metrics",
    "segments": "Segments",
    "virtual_report_suites": "Virtual Report Suites",
}


def reference_display_rows(doc: Any) -> list[list[str]]:
    """References appendix rows with human family and relation labels."""
    from aa_auto_sdr.sdr.definitions import build_references, reference_rows

    out: list[list[str]] = []
    for family, ident, name, relation, kind, target_family, target_id, target_name, status in reference_rows(
        build_references(doc)
    ):
        out.append(
            [
                _FAMILY_LABELS.get(family, family),
                ident,
                name,
                relation.replace("_", " "),
                kind,
                _FAMILY_LABELS.get(target_family, target_family),
                target_id,
                target_name,
                status,
            ]
        )
    return out


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
