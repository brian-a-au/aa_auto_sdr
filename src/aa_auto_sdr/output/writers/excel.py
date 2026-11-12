"""Excel writer — multi-sheet workbook, frozen header row, autofilter on every sheet.

Writes the workbook with xlsxwriter directly. The heavy import is deferred to
method scope so the registry can be loaded without paying the import cost on
fast paths.

Cells are written header first, then one column at a time, top to bottom. That
order fixes the shared-string table, so the workbook is byte-for-byte the one
the earlier pandas-based writer produced (`tests/output/test_writer_excel_parity.py`).

Self-registers with the registry on import."""

from __future__ import annotations

import logging
import time
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.atomic_io import atomic_write_path
from aa_auto_sdr.output._helpers import (
    REFERENCE_HEADINGS,
    component_headers,
    component_values,
    reference_display_rows,
    render_provenance_pairs,
    stringify_cell,
)
from aa_auto_sdr.output.coverage import (
    QUALITY_ISSUE_COLUMNS,
    coverage_rows,
    quality_issue_cells,
    quality_status,
    quality_status_line,
)
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)

_FAMILY_SHEETS: dict[str, str] = {
    "Dimensions": "dimensions",
    "Metrics": "metrics",
    "Segments": "segments",
    "Calculated Metrics": "calculated_metrics",
    "Virtual Report Suites": "virtual_report_suites",
    "Classifications": "classifications",
}

# One table may hold at most this many data rows and columns (the header row
# is not counted). Larger tables raise instead of losing rows.
_MAX_ROWS = 2**20
_MAX_COLS = 2**14
# Excel's cell limit. xlsxwriter truncates longer strings; the writer warns.
_CELL_MAX_CHARS = 32767


class ExcelWriter:
    extension = ".xlsx"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)

        target.parent.mkdir(parents=True, exist_ok=True)

        def serialize(staged: Path) -> None:
            import xlsxwriter
            from xlsxwriter.exceptions import FileCreateError

            try:
                # strings_to_formulas/urls off: xlsxwriter otherwise converts any
                # leading-`=` string (user-authored component names) into a LIVE
                # formula cell, and URL-looking strings into hyperlinks.
                with xlsxwriter.Workbook(
                    str(staged),
                    {"strings_to_formulas": False, "strings_to_urls": False},
                ) as book:
                    _write_sheet(book, "Summary", ["Field", "Value"], _summary_rows(doc))
                    _write_sheet(
                        book,
                        "Coverage",
                        ["Family", "State", "Count", "Expansion Level"],
                        _coverage_rows(doc),
                    )
                    _write_quality_sheet(book, doc)
                    for name, family in _FAMILY_SHEETS.items():
                        headers, rows = _component_table(family, getattr(doc, family))
                        _write_sheet(book, name, headers, rows)
                    _write_sheet(book, "References", list(REFERENCE_HEADINGS), reference_display_rows(doc))
            except FileCreateError as exc:
                # xlsxwriter wraps the OSError from saving (e.g. a full disk);
                # unwrap it so callers map it to an output failure (exit 15).
                cause = exc.args[0] if exc.args else None
                raise (cause if isinstance(cause, OSError) else OSError(str(exc))) from exc

        atomic_write_path(target, serialize)
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "output_write format=excel output_path=%s count=1 duration_ms=%s",
            str(target),
            duration_ms,
            extra={
                "format": "excel",
                "output_path": str(target),
                "count": 1,
                "duration_ms": duration_ms,
                "rsid": doc.report_suite.rsid,
            },
        )
        return [target]


def _add_sheet(book: Any, name: str, num_rows: int, num_cols: int) -> Any:
    """Add a worksheet, refusing a table larger than one sheet can hold."""
    _check_size(num_rows, num_cols)
    return book.add_worksheet(name)


def _check_size(num_rows: int, num_cols: int) -> None:
    if num_rows > _MAX_ROWS or num_cols > _MAX_COLS:
        raise ValueError(
            f"This sheet is too large! Your sheet size is: {num_rows}, {num_cols} "
            f"Max sheet size is: {_MAX_ROWS}, {_MAX_COLS}"
        )


def _write_table(ws: Any, start_row: int, headers: Sequence[Any], rows: Sequence[Sequence[Any]]) -> list[int]:
    """Write a header row at `start_row` and the rows below it, one column at a time.

    Returns the longest cell length per column (0 for a column with no rows).
    An empty string or None leaves the cell empty."""
    write = ws.write
    for col, header in enumerate(headers):
        _write_cell(write, start_row, col, header)
    longest: list[int] = []
    for col in range(len(headers)):
        best = 0
        for row_idx, row in enumerate(rows, start=start_row + 1):
            value = row[col]
            if isinstance(value, str):
                length = len(value)
                if length > _CELL_MAX_CHARS:
                    _warn_truncated()
                if length:
                    write(row_idx, col, value)
            else:
                length = len(str(value))
                if value is not None:
                    write(row_idx, col, value)
            if length > best:
                best = length
        longest.append(best)
    return longest


def _write_cell(write: Any, row: int, col: int, value: Any) -> None:
    if isinstance(value, str):
        if len(value) > _CELL_MAX_CHARS:
            _warn_truncated()
        if value:
            write(row, col, value)
    elif value is not None:
        write(row, col, value)


def _warn_truncated() -> None:
    warnings.warn("Cell contents too long, truncated to 32767 characters", UserWarning, stacklevel=2)


def _write_sheet(book: Any, name: str, headers: list[str], rows: list[list[Any]]) -> None:
    """One table sheet: header row, frozen; autofilter and fitted widths when it has columns."""
    ws = _add_sheet(book, name, len(rows), len(headers))
    longest = _write_table(ws, 0, headers, rows)
    ws.freeze_panes(1, 0)
    if headers and rows:
        ws.autofilter(0, 0, len(rows), len(headers) - 1)
    for col_idx, header in enumerate(headers):
        width = max(len(str(header)), longest[col_idx] or 10)
        ws.set_column(col_idx, col_idx, min(width + 2, 60))


def _summary_rows(doc: SdrDocument) -> list[list[Any]]:
    return [
        ["RSID", doc.report_suite.rsid],
        ["Name", doc.report_suite.name],
        ["Timezone", doc.report_suite.timezone or ""],
        ["Captured at", doc.captured_at.isoformat()],
        ["Tool version", doc.tool_version],
        *([field, value] for field, value in render_provenance_pairs(doc)),
        ["Dimensions", len(doc.dimensions)],
        ["Metrics", len(doc.metrics)],
        ["Segments", len(doc.segments)],
        ["Calculated Metrics", len(doc.calculated_metrics)],
        ["Virtual Report Suites", len(doc.virtual_report_suites)],
        ["Classifications", len(doc.classifications)],
    ]


def _coverage_rows(doc: SdrDocument) -> list[list[Any]]:
    return [[row.heading, row.label, row.count, row.expansion_level or ""] for row in coverage_rows(doc)]


_ISSUE_COLUMNS = QUALITY_ISSUE_COLUMNS


def _write_quality_sheet(book: Any, doc: SdrDocument) -> None:
    """Quality sheet: a summary block, a blank row, then one row per issue.

    When no audit ran the sheet holds a single row saying so."""
    status = quality_status(doc.quality)
    if not status.audited:
        line = quality_status_line(status)
        ws = _add_sheet(book, "Quality", 1, 1)
        _write_cell(ws.write, 0, 0, line)
        # The column has no header; its label is the column index, 0.
        ws.set_column(0, 0, min(max(len("0"), len(line) or 10) + 2, 60))
        return

    summary_headers = ["Field", "Value"]
    summary_rows: list[list[Any]] = [
        ["Verdict", status.verdict or "n/a"],
        ["Policy threshold", status.threshold or ""],
        ["Total issues", status.total],
    ]
    summary_rows.extend([sev, n] for sev, n in (status.by_severity or {}).items())
    # Last and only when non-zero, so a workbook without exceptions keeps the
    # same summary layout and issue-table position as before.
    if status.excepted:
        summary_rows.append(["Excepted", status.excepted])
    ws = _add_sheet(book, "Quality", len(summary_rows), len(summary_headers))
    _write_table(ws, 0, summary_headers, summary_rows)

    issues_start = len(summary_rows) + 2  # header row + rows + one blank row
    issue_rows = [quality_issue_cells(issue) for issue in status.issues]
    _check_size(len(issue_rows), len(_ISSUE_COLUMNS))
    _write_table(ws, issues_start, _ISSUE_COLUMNS, issue_rows)
    if issue_rows:
        ws.autofilter(issues_start, 0, issues_start + len(issue_rows), len(_ISSUE_COLUMNS) - 1)
    for col_idx, col in enumerate(_ISSUE_COLUMNS):
        values = [col, *(row[col_idx] for row in issue_rows)]
        if col_idx < len(summary_headers):
            values += [summary_headers[col_idx], *(row[col_idx] for row in summary_rows)]
        longest = max(len(str(v)) for v in values)
        ws.set_column(col_idx, col_idx, min(max(longest, 10) + 2, 60))


def _component_table(family: str, items: list[Any]) -> tuple[list[str], list[list[str]]]:
    """Headers and stringified rows for one component sheet.

    Segments and calculated metrics gain the derived definition columns
    after the model fields. An empty family has no columns at all."""
    if not items:
        return [], []
    headers = component_headers(family, type(items[0]))
    rows = [[stringify_cell(v) for v in component_values(family, item)] for item in items]
    return headers, rows


register_writer("excel", ExcelWriter())
