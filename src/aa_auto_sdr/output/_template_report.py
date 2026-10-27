"""Overflow and coverage sheets for the template-fill Excel writer.

The fill engine bounds each template sheet at `max_row + 50` rows. Rows past
that cap are collected as `OverflowRow`s and written to a separate `Overflow`
sheet, so no row the API supplied is lost. A `Template Coverage` sheet then
reports, per template sheet, what was matched, appended, or sent to overflow,
which sheets or anchors were missing, and which template columns the writer
cannot fill, plus the per-family coverage state shared by every report format.

Both sheets are new sheets appended after the template's own sheets, so they
never touch a template region. No openpyxl import: the functions only call
methods on the workbook the writer already loaded."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from aa_auto_sdr.output.coverage import FAMILY_HEADINGS, coverage_rows, quality_status, quality_status_line
from aa_auto_sdr.sdr.document import SdrDocument

OVERFLOW_SHEET = "Overflow"
COVERAGE_SHEET = "Template Coverage"

# Which template sheets each component family can land in. Families absent
# here have no template sheet.
TEMPLATE_SHEETS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "dimensions": ("eVars", "props"),
    "metrics": ("custom events (metrics)",),
    "segments": ("metrics-segments",),
    "calculated_metrics": ("metrics-segments",),
}

_OVERFLOW_KEY_HEADERS = ("Template Sheet", "Reason", "Component Type", "Component ID")

# Overflow `Reason` values: why a row is not in its template sheet.
REASON_CLIPPED = "clipped"
SKIP_REASONS: dict[str, str] = {
    "missing_or_unanchored": "sheet missing or unanchored",
    "no_id_column": "sheet has no id column",
}
_SHEET_HEADERS = (
    "Template Sheet",
    "Status",
    "Reason",
    "Components",
    "Rows Matched",
    "Rows Appended",
    "Rows In Overflow",
    "Unsupported Columns",
    "Missing Columns",
)
_FAMILY_HEADERS = ("Family", "State", "Count", "Expansion Level", "Template Sheets")

SetCell = Callable[..., None]


@dataclass(frozen=True, slots=True)
class OverflowRow:
    """One row that is not in its template sheet: clipped by the soft cap,
    or meant for a template sheet that was skipped. `reason` is
    `REASON_CLIPPED` or a `SKIP_REASONS` value."""

    source_sheet: str
    reason: str
    component_type: str
    component_id: str
    values: dict[str, Any]


@dataclass(slots=True)
class SheetFillReport:
    """What happened to one template sheet during a fill."""

    sheet: str
    status: str  # "filled" or "skipped"
    reason: str | None = None
    components: int = 0
    rows_matched: int = 0
    rows_appended: int = 0
    overflow: list[OverflowRow] = field(default_factory=list)
    unsupported_columns: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()


def column_gaps(
    template_columns: Iterable[str], writer_columns: Iterable[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (unsupported, missing).

    Unsupported: template headers the writer has no data for. The `ID` column
    is customer numbering and is never written, so it is not a gap.
    Missing: headers the writer would fill that the template does not have."""
    template = list(template_columns)
    writer = list(writer_columns)
    unsupported = tuple(h for h in template if h not in writer and h != "ID")
    missing = tuple(h for h in writer if h not in template)
    return unsupported, missing


def unique_sheet_name(wb, base: str) -> str:
    """`base`, or `base (2)`, `base (3)`, ... when the template already uses it.

    Excel sheet names are case-insensitive, so `overflow` blocks `Overflow`."""
    taken = {name.lower() for name in wb.sheetnames}
    if base.lower() not in taken:
        return base
    n = 2
    while f"{base} ({n})".lower() in taken:
        n += 1
    return f"{base} ({n})"


def write_overflow_sheet(wb, rows: list[OverflowRow], set_cell: SetCell) -> str:
    """Append the Overflow sheet and return its name.

    Columns: the row's source template sheet, why it is here, component type
    and id, then every template column any overflow row carries a value for,
    in order of first appearance."""
    ws = wb.create_sheet(unique_sheet_name(wb, OVERFLOW_SHEET))
    value_headers: list[str] = []
    for row in rows:
        for header in row.values:
            if header not in value_headers:
                value_headers.append(header)
    headers = [*_OVERFLOW_KEY_HEADERS, *value_headers]
    for col, header in enumerate(headers, start=1):
        set_cell(ws, row=1, col=col, value=header)
    for r, row in enumerate(rows, start=2):
        for col, value in enumerate((row.source_sheet, row.reason, row.component_type, row.component_id), start=1):
            set_cell(ws, row=r, col=col, value=value)
        for header, value in row.values.items():
            set_cell(ws, row=r, col=len(_OVERFLOW_KEY_HEADERS) + 1 + value_headers.index(header), value=value)
    ws.freeze_panes = "A2"
    return ws.title


def write_coverage_sheet(
    wb,
    doc: SdrDocument,
    reports: list[SheetFillReport],
    overflow_sheet: str | None,
    set_cell: SetCell,
) -> str:
    """Append the Template Coverage sheet and return its name.

    Three blocks separated by a blank row: a Measure/Value summary, one row
    per template sheet, and one row per component family."""
    ws = wb.create_sheet(unique_sheet_name(wb, COVERAGE_SHEET))
    row = 1

    def put(values: Iterable[Any]) -> None:
        nonlocal row
        for col, value in enumerate(values, start=1):
            if value is not None:
                set_cell(ws, row=row, col=col, value=value)
        row += 1

    overflow = [o for r in reports for o in r.overflow]
    clipped = sum(1 for o in overflow if o.reason == REASON_CLIPPED)
    put(["Template Coverage"])
    row += 1
    put(["Measure", "Value"])
    put(["Components", sum(r.components for r in reports)])
    put(["Rows matched", sum(r.rows_matched for r in reports)])
    put(["Rows appended", sum(r.rows_appended for r in reports)])
    put(["Rows sent to Overflow", len(overflow)])
    put(["Rows clipped by soft cap", clipped])
    put(["Rows from skipped sheets", len(overflow) - clipped])
    put(["Overflow sheet", overflow_sheet or "none"])
    put(["Sheets skipped", sum(1 for r in reports if r.status == "skipped")])
    put(["Quality", quality_status_line(quality_status(doc.quality))])
    row += 1

    put(_SHEET_HEADERS)
    for r in reports:
        put(
            [
                r.sheet,
                r.status,
                r.reason,
                r.components,
                r.rows_matched,
                r.rows_appended,
                len(r.overflow),
                ", ".join(r.unsupported_columns) or None,
                ", ".join(r.missing_columns) or None,
            ]
        )
    row += 1

    put(_FAMILY_HEADERS)
    for cov in coverage_rows(doc):
        put(
            [
                FAMILY_HEADINGS[cov.family],
                cov.label,
                cov.count,
                cov.expansion_level,
                ", ".join(TEMPLATE_SHEETS_BY_FAMILY.get(cov.family, ())) or "not in template",
            ]
        )
    return ws.title
