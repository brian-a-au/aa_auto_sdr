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


def escape_pipe(text: str) -> str:
    """Escape Markdown-table-breaking characters in a cell value.

    Pipes become \\|. Newlines become <br> (GFM-supported)."""
    return text.replace("|", r"\|").replace("\n", "<br>")


def escape_html(text: str) -> str:
    """Escape HTML special characters. Wraps stdlib html.escape."""
    return _html.escape(text, quote=True)
