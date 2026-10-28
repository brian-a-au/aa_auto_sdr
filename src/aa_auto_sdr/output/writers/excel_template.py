"""Template-fill Excel writer.

Opens an existing Adobe BRD/SDR `.xlsx` template, locates each data sheet by
name + section anchor, finds the header row by content, and fills component
data into the rows below. Preserves styles, cross-sheet formulas, defined
names, column widths, page setup, and every cell not explicitly written.
Rows past each sheet's soft cap go to an appended `Overflow` sheet, and a
`Template Coverage` sheet reports what landed where (see `_template_report`).

Heavy import (`openpyxl`) is deferred to method scope so the registry can be
bootstrapped on fast paths without paying the import cost. Mirrors the
deferred-pandas pattern in `excel.py`.

Self-registers under the `excel-template` format key on import.

Read-only AA 2.0 invariant: `openpyxl` writes target local `.xlsx` files only,
never the Adobe Analytics API."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.atomic_io import atomic_write_path
from aa_auto_sdr.output._template_anchors import ANCHORS, SheetAnchor, resolve_sheet
from aa_auto_sdr.output._template_report import (
    REASON_CLIPPED,
    SKIP_REASONS,
    OverflowRow,
    SheetFillReport,
    column_gaps,
    write_coverage_sheet,
    write_overflow_sheet,
)
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


def _normalize_id(raw_id: str) -> str:
    """Strip the AA 2.0 namespace prefix (`variables/` for dimensions,
    `metrics/` for metrics) so component ids can be matched against the
    template's cell values, which are bare implementation ids
    (e.g. `campaign`, `pageName`, `eVar1`).

    Returns the bare id when there's no namespace; otherwise drops the
    leading `<ns>/` segment. Always returns the result as-is (callers
    handle case-folding via `.lower()` where appropriate).
    """
    if "/" in raw_id:
        return raw_id.split("/", 1)[1]
    return raw_id


def _calc_format_label(cm: Any) -> str | None:
    """Map (precision, type) → 'Percent' / 'Decimal' / 'Time' / 'Currency'.

    Returns None when the mapping is uncertain — under-fill is safer than
    wrong-fill (§8). Spec spike confirms 'percent' / 'currency' / 'time'
    are the API's documented `type` values for calc metrics; 'decimal' is
    the default for numeric precision > 0.
    """
    t = (cm.type or "").lower()
    if t == "percent":
        return "Percent"
    if t == "currency":
        return "Currency"
    if t == "time":
        return "Time"
    if t == "decimal" or cm.precision > 0:
        return "Decimal"
    return None


class ExcelTemplateWriter:
    extension = ".xlsx"

    def __init__(self) -> None:
        self.template_path: Path | None = None
        self.organization: str | None = None

    # ---- shared sheet-fill engine -------------------------------------------

    def _fill_by_id_sheet(
        self,
        wb,
        *,
        anchor: SheetAnchor,
        id_column_header: str,
        component_type: str,
        components: Iterable[Any],
        get_id: Callable[[Any], str],
        column_map: dict[str, Callable[[Any], Any]],
    ) -> SheetFillReport:
        """Locate a sheet, build the column index, fill rows by id-match.

        - `id_column_header`: the column whose value is the row's component id
          (e.g. 'Analytics Variable' for dimensions, 'Event' for events).
        - `component_type`: label for rows sent to the Overflow sheet.
        - `column_map`: header text → getter that returns the value to write
          for a given component. Headers absent from the sheet's column map
          are skipped (the template may not expose every column) and reported
          as missing columns.
        - Non-empty rule (§3.7): only write when the value is non-empty after
          stripping; never blank-overwrite an existing styled cell.
        - Soft cap: never append past max_row + 50 rows. Rows past the cap are
          returned as overflow rows for the Overflow sheet, never dropped.
        - Skipped sheet: every component meant for it is returned as an
          overflow row, so a missing sheet never loses rows either.
        """
        components = list(components)
        writer_map = {id_column_header: get_id, **column_map}

        def skipped(reason: str, **gaps: tuple[str, ...]) -> SheetFillReport:
            _log_sheet_skipped(anchor.sheet_name, reason)
            return SheetFillReport(
                anchor.sheet_name,
                "skipped",
                reason=reason,
                components=len(components),
                overflow=[
                    _overflow_row(
                        anchor.sheet_name, SKIP_REASONS[reason], component_type, get_id(c), None, writer_map, c
                    )
                    for c in components
                ],
                **gaps,
            )

        resolved = resolve_sheet(wb, anchor)
        if resolved is None:
            return skipped("missing_or_unanchored")

        ws = wb[resolved.sheet_name]
        unsupported, missing = column_gaps(resolved.columns, column_map)
        if id_column_header not in resolved.columns:
            return skipped("no_id_column", unsupported_columns=unsupported, missing_columns=missing)

        report = SheetFillReport(
            anchor.sheet_name,
            "filled",
            components=len(components),
            unsupported_columns=unsupported,
            missing_columns=missing,
        )
        id_col = resolved.columns[id_column_header]
        wanted = {get_id(c).lower(): c for c in components}
        if not wanted:
            return report

        for row in range(resolved.first_data_row, ws.max_row + 1):
            existing_id = ws.cell(row=row, column=id_col).value
            if existing_id is None:
                continue
            key = str(existing_id).strip().lower()
            if key not in wanted:
                continue
            comp = wanted.pop(key)
            _write_row(ws, row=row, columns=resolved.columns, column_map=column_map, comp=comp)
            report.rows_matched += 1

        # Append path for components the template didn't pre-seed. The soft
        # cap bounds the template sheet at +50 rows past max_row; anything
        # beyond goes to the Overflow sheet.
        soft_cap = ws.max_row + 50
        append_row = ws.max_row + 1
        for comp in wanted.values():
            if append_row > soft_cap:
                report.overflow.append(
                    _overflow_row(
                        anchor.sheet_name,
                        REASON_CLIPPED,
                        component_type,
                        get_id(comp),
                        resolved.columns,
                        writer_map,
                        comp,
                    )
                )
                continue
            _set_text_safe_cell(ws, row=append_row, col=id_col, value=get_id(comp))
            _write_row(ws, row=append_row, columns=resolved.columns, column_map=column_map, comp=comp)
            append_row += 1
            report.rows_appended += 1

        _log_sheet_filled(report, soft_cap)
        return report

    # ---- dimensions ---------------------------------------------------------

    def _fill_dimensions(self, wb, doc: SdrDocument) -> list[SheetFillReport]:
        # AA 2.0 returns ids like `variables/campaign`; templates use bare ids
        # like `campaign`. Match on the stripped id throughout.
        evar_components = [
            d
            for d in doc.dimensions
            if _normalize_id(d.id).lower().startswith("evar") or _normalize_id(d.id).lower() == "campaign"
        ]
        prop_components = [
            d
            for d in doc.dimensions
            if _normalize_id(d.id).lower().startswith("prop") or _normalize_id(d.id).lower() in {"pagename", "linkname"}
        ]
        column_map: dict[str, Callable[[Any], Any]] = {
            "Analytics Variable": lambda d: _normalize_id(d.id),
            "Variable Name": lambda d: d.name,
            "Variable Description": lambda d: d.description,
        }
        return [
            self._fill_by_id_sheet(
                wb,
                anchor=ANCHORS["evars"],
                id_column_header="Analytics Variable",
                component_type="Dimension",
                components=evar_components,
                get_id=lambda d: _normalize_id(d.id),
                column_map=column_map,
            ),
            self._fill_by_id_sheet(
                wb,
                anchor=ANCHORS["props"],
                id_column_header="Analytics Variable",
                component_type="Dimension",
                components=prop_components,
                get_id=lambda d: _normalize_id(d.id),
                column_map=column_map,
            ),
        ]

    def _fill_metrics(self, wb, doc: SdrDocument) -> SheetFillReport:
        # AA 2.0 returns ids like `metrics/event1`; match on the stripped id.
        custom_events = [m for m in doc.metrics if _normalize_id(m.id).lower().startswith("event")]
        column_map: dict[str, Callable[[Any], Any]] = {
            "Event": lambda m: _normalize_id(m.id),
            "Event Name": lambda m: m.name,
            "Event Description": lambda m: m.description,
        }
        return self._fill_by_id_sheet(
            wb,
            anchor=ANCHORS["events"],
            id_column_header="Event",
            component_type="Metric",
            components=custom_events,
            get_id=lambda m: _normalize_id(m.id),
            column_map=column_map,
        )

    def _fill_metrics_segments(self, wb, doc: SdrDocument) -> SheetFillReport:
        """Combined sheet: calc metrics + segments. Type literal derived from
        the source list; Format derived from calc-metric type/precision.

        Calculated metrics come first, so when the soft cap is reached the
        rows past it (often segments) go to the Overflow sheet."""
        anchor = ANCHORS["metrics_segments"]
        calc_map: dict[str, Callable[[Any], Any]] = {
            "Type": lambda _c: "Calculated Metric",
            "Name": lambda c: c.name,
            "Description": lambda c: c.description,
            "Format": _calc_format_label,
        }
        seg_map: dict[str, Callable[[Any], Any]] = {
            "Type": lambda _s: "Segment",
            "Name": lambda s: s.name,
            "Description": lambda s: s.description,
            # No Format column for segments.
        }
        entries: list[tuple[str, str, Any, dict[str, Callable[[Any], Any]]]] = [
            ("Calculated Metric", cm.id, cm, calc_map) for cm in doc.calculated_metrics
        ]
        entries.extend(("Segment", seg.id, seg, seg_map) for seg in doc.segments)

        def skipped(reason: str, **gaps: tuple[str, ...]) -> SheetFillReport:
            _log_sheet_skipped(anchor.sheet_name, reason)
            return SheetFillReport(
                anchor.sheet_name,
                "skipped",
                reason=reason,
                components=len(entries),
                overflow=[
                    _overflow_row(anchor.sheet_name, SKIP_REASONS[reason], ctype, cid, None, cmap, comp)
                    for ctype, cid, comp, cmap in entries
                ],
                **gaps,
            )

        resolved = resolve_sheet(wb, anchor)
        if resolved is None:
            return skipped("missing_or_unanchored")

        unsupported, missing = column_gaps(resolved.columns, calc_map)
        if not any(header in resolved.columns for header in calc_map):
            # Renamed headers: a row here would be counted but hold no cell.
            return skipped("no_known_columns", unsupported_columns=unsupported, missing_columns=missing)
        report = SheetFillReport(
            anchor.sheet_name,
            "filled",
            components=len(entries),
            unsupported_columns=unsupported,
            missing_columns=missing,
        )
        if not entries:
            return report

        # No id column to match on for this sheet (calc metric ids and
        # segment ids are opaque GUIDs that the template wouldn't pre-seed).
        # Always append; soft-cap at max_row + 50, overflow past it.
        ws = wb[anchor.sheet_name]
        append_row = ws.max_row + 1
        soft_cap = ws.max_row + 50
        for component_type, comp_id, comp, column_map in entries:
            if append_row > soft_cap:
                report.overflow.append(
                    _overflow_row(
                        anchor.sheet_name, REASON_CLIPPED, component_type, comp_id, resolved.columns, column_map, comp
                    )
                )
                continue
            _write_row(ws, row=append_row, columns=resolved.columns, column_map=column_map, comp=comp)
            append_row += 1
            report.rows_appended += 1

        _log_sheet_filled(report, soft_cap)
        return report

    def _fill_glossary_org(self, wb, doc: SdrDocument) -> SheetFillReport:
        """Write the org name to Glossary!C2 — the source-of-truth cell
        every other sheet's C2 formula references. Skips if 'Glossary' is
        absent (defensive — real Adobe templates always include it)."""
        if "Glossary" not in wb.sheetnames:
            return SheetFillReport("Glossary", "skipped", reason="missing")
        org = self.organization or doc.report_suite.name
        _set_text_safe_cell(wb["Glossary"], row=2, col=3, value=org)
        return SheetFillReport("Glossary", "filled")

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        if self.template_path is None:
            raise RuntimeError(
                "ExcelTemplateWriter dispatched without template_path; CLI validator should have caught this.",
            )
        from openpyxl import load_workbook  # method-scoped lazy import

        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        wb = load_workbook(self.template_path)  # data_only=False; preserve formulas

        logger.info(
            "template_load path=%s sheets=%d",
            str(self.template_path),
            len(wb.sheetnames),
            extra={"path": str(self.template_path), "sheets": len(wb.sheetnames)},
        )

        reports = [self._fill_glossary_org(wb, doc)]
        reports.extend(self._fill_dimensions(wb, doc))
        reports.append(self._fill_metrics(wb, doc))
        reports.append(self._fill_metrics_segments(wb, doc))

        # Both report sheets are appended after the template's own sheets,
        # outside every template region.
        overflow = [row for report in reports for row in report.overflow]
        overflow_sheet: str | None = None
        if overflow:
            overflow_sheet = write_overflow_sheet(wb, overflow, _set_text_safe_cell)
            logger.warning(
                "template_overflow_sheet_written sheet=%s count=%d",
                overflow_sheet,
                len(overflow),
                extra={"sheet": overflow_sheet, "count": len(overflow)},
            )
        write_coverage_sheet(wb, doc, reports, overflow_sheet, _set_text_safe_cell)

        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_path(target, wb.save)

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "output_write format=excel-template output_path=%s count=1 duration_ms=%s",
            str(target),
            duration_ms,
            extra={
                "format": "excel-template",
                "output_path": str(target),
                "count": 1,
                "duration_ms": duration_ms,
                "rsid": doc.report_suite.rsid,
            },
        )
        return [target]


def _log_sheet_skipped(sheet: str, reason: str) -> None:
    logger.warning(
        "template_sheet_skipped sheet=%s reason=%s",
        sheet,
        reason,
        extra={"sheet": sheet, "reason": reason},
    )


def _log_sheet_filled(report: SheetFillReport, soft_cap: int) -> None:
    logger.info(
        "template_sheet_filled sheet=%s rows_matched=%d rows_appended=%d",
        report.sheet,
        report.rows_matched,
        report.rows_appended,
        extra={
            "sheet": report.sheet,
            "rows_matched": report.rows_matched,
            "rows_appended": report.rows_appended,
        },
    )
    if report.rows_appended > 0:
        logger.warning(
            "template_overflow sheet=%s overflow_rows=%d",
            report.sheet,
            report.rows_appended,
            extra={"sheet": report.sheet, "overflow_rows": report.rows_appended},
        )
    if report.overflow:
        logger.warning(
            "template_sheet_clipped sheet=%s rows_dropped=%d soft_cap=%d",
            report.sheet,
            len(report.overflow),
            soft_cap,
            extra={
                "sheet": report.sheet,
                "rows_dropped": len(report.overflow),
                "soft_cap": soft_cap,
            },
        )


def _overflow_row(
    sheet: str,
    reason: str,
    component_type: str,
    component_id: str,
    columns: dict[str, int] | None,
    column_map: dict[str, Callable[[Any], Any]],
    comp: Any,
) -> OverflowRow:
    """Capture the values a template sheet would have received, keyed by the
    template's column headers, for a row that is not in that sheet.

    `columns` is the resolved sheet's header map, which limits values to
    columns the sheet has. It is None for a skipped sheet, where there is no
    header map, so every column the writer would fill is kept."""
    values: dict[str, Any] = {}
    for header, getter in column_map.items():
        if columns is not None and header not in columns:
            continue
        value = getter(comp)
        if value is None or not str(value).strip():
            continue
        values[header] = value
    return OverflowRow(sheet, reason, component_type, component_id, values)


def _write_row(
    ws,
    *,
    row: int,
    columns: dict[str, int],
    column_map: dict[str, Callable[[Any], Any]],
    comp: Any,
) -> None:
    """Write one component's values into a row, honoring the non-empty rule.

    Never writes None / empty over an existing styled cell — preserves the
    template's example content when the API has no data for that field.
    Headers absent from `columns` (i.e. not in this sheet) are silently
    skipped."""
    for header, getter in column_map.items():
        col = columns.get(header)
        if col is None:
            continue
        value = getter(comp)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        _set_text_safe_cell(ws, row=row, col=col, value=value)


def _set_text_safe_cell(ws, *, row: int, col: int, value: Any) -> None:
    """Write a cell, forcing string type when openpyxl would infer a formula.

    openpyxl marks any string starting with `=` as data_type 'f' (a live
    formula). Component names are user-authored in Adobe Analytics, so a name
    like `=HYPERLINK(...)` must land as literal text, not executable content.

    Control characters a worksheet cannot store (a vertical tab from a pasted
    Word line break, for one) are dropped; openpyxl would raise on them."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE  # method-scoped lazy import

    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
    cell = ws.cell(row=row, column=col, value=value)
    if cell.data_type == "f":
        cell.data_type = "s"


register_writer("excel-template", ExcelTemplateWriter())
