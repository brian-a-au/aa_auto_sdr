"""Excel writer — multi-sheet workbook, frozen header row, autofilter on every sheet.

Heavy imports (pandas, xlsxwriter) are deferred to method scope so the registry
can be loaded without paying the import cost on fast paths.

Self-registers with the registry on import."""

from __future__ import annotations

import logging
import time
from dataclasses import fields
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.atomic_io import atomic_write_path
from aa_auto_sdr.output._helpers import render_provenance_pairs, stringify_cell
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


class ExcelWriter:
    extension = ".xlsx"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)

        import pandas as pd

        sheets = {
            "Summary": None,
            "Coverage": None,
            "Quality": None,
            "Dimensions": doc.dimensions,
            "Metrics": doc.metrics,
            "Segments": doc.segments,
            "Calculated Metrics": doc.calculated_metrics,
            "Virtual Report Suites": doc.virtual_report_suites,
            "Classifications": doc.classifications,
        }

        target.parent.mkdir(parents=True, exist_ok=True)
        # strings_to_formulas/urls off: xlsxwriter otherwise converts any
        # leading-`=` string (user-authored component names) into a LIVE
        # formula cell, and URL-looking strings into hyperlinks.
        engine_kwargs = {"options": {"strings_to_formulas": False, "strings_to_urls": False}}

        def serialize(staged: Path) -> None:
            with pd.ExcelWriter(staged, engine="xlsxwriter", engine_kwargs=engine_kwargs) as xl:
                for name, items in sheets.items():
                    if name == "Quality":
                        _write_quality_sheet(xl, doc)
                        continue
                    if name == "Summary":
                        df = _summary_df(doc)
                    elif name == "Coverage":
                        df = _coverage_df(doc)
                    else:
                        df = _component_df(items)
                    df.to_excel(xl, sheet_name=name, index=False)
                    ws = xl.sheets[name]
                    ws.freeze_panes(1, 0)
                    if df.shape[1] > 0 and df.shape[0] > 0:
                        ws.autofilter(0, 0, df.shape[0], df.shape[1] - 1)
                    _fit_columns(ws, df)
                    del df

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


def _fit_columns(ws: Any, df: Any) -> None:
    for col_idx, col in enumerate(df.columns):
        # Component-sheet cells are already strings (stringify_cell);
        # str() on the Summary sheet's mixed values matches what
        # astype(str) produced, without a full column re-conversion.
        longest = max((len(v) if isinstance(v, str) else len(str(v)) for v in df[col]), default=0)
        width = max(len(str(col)), longest or 10)
        ws.set_column(col_idx, col_idx, min(width + 2, 60))


def _summary_df(doc: SdrDocument):
    import pandas as pd

    return pd.DataFrame(
        [
            ("RSID", doc.report_suite.rsid),
            ("Name", doc.report_suite.name),
            ("Timezone", doc.report_suite.timezone or ""),
            ("Captured at", doc.captured_at.isoformat()),
            ("Tool version", doc.tool_version),
            *render_provenance_pairs(doc),
            ("Dimensions", len(doc.dimensions)),
            ("Metrics", len(doc.metrics)),
            ("Segments", len(doc.segments)),
            ("Calculated Metrics", len(doc.calculated_metrics)),
            ("Virtual Report Suites", len(doc.virtual_report_suites)),
            ("Classifications", len(doc.classifications)),
        ],
        columns=["Field", "Value"],
    )


def _coverage_df(doc: SdrDocument):
    import pandas as pd

    return pd.DataFrame(
        [(row.heading, row.label, row.count, row.expansion_level or "") for row in coverage_rows(doc)],
        columns=["Family", "State", "Count", "Expansion Level"],
    )


_ISSUE_COLUMNS = QUALITY_ISSUE_COLUMNS


def _write_quality_sheet(xl: Any, doc: SdrDocument) -> None:
    """Quality sheet: a summary block, a blank row, then one row per issue.

    When no audit ran the sheet holds a single row saying so."""
    import pandas as pd

    status = quality_status(doc.quality)
    if not status.audited:
        df = pd.DataFrame([[quality_status_line(status)]])
        df.to_excel(xl, sheet_name="Quality", index=False, header=False)
        _fit_columns(xl.sheets["Quality"], df)
        return

    summary_rows: list[tuple[str, Any]] = [
        ("Verdict", status.verdict or "n/a"),
        ("Policy threshold", status.threshold or ""),
        ("Total issues", status.total),
        ("Excepted", status.excepted),
    ]
    summary_rows.extend((sev, n) for sev, n in (status.by_severity or {}).items())
    summary_df = pd.DataFrame(summary_rows, columns=["Field", "Value"])
    summary_df.to_excel(xl, sheet_name="Quality", index=False)

    issues_start = len(summary_rows) + 2  # header row + rows + one blank row
    issues_df = pd.DataFrame(
        [quality_issue_cells(issue) for issue in status.issues],
        columns=_ISSUE_COLUMNS,
    )
    issues_df.to_excel(xl, sheet_name="Quality", index=False, startrow=issues_start)
    ws = xl.sheets["Quality"]
    if issues_df.shape[0] > 0:
        ws.autofilter(issues_start, 0, issues_start + issues_df.shape[0], issues_df.shape[1] - 1)
    for col_idx, col in enumerate(_ISSUE_COLUMNS):
        values = [col, *issues_df[col]]
        if col_idx < summary_df.shape[1]:
            values += [summary_df.columns[col_idx], *summary_df.iloc[:, col_idx]]
        longest = max(len(str(v)) for v in values)
        ws.set_column(col_idx, col_idx, min(max(longest, 10) + 2, 60))


def _component_df(items: list[Any]):
    """Build a DataFrame for one component sheet, stringifying nested values."""
    import pandas as pd

    if not items:
        return pd.DataFrame()
    flat = [{field.name: stringify_cell(getattr(item, field.name)) for field in fields(item)} for item in items]
    return pd.DataFrame(flat)


register_writer("excel", ExcelWriter())
