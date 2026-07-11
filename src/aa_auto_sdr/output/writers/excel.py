"""Excel writer — multi-sheet workbook, frozen header row, autofilter on every sheet.

Heavy imports (pandas, xlsxwriter) are deferred to method scope so the registry
can be loaded without paying the import cost on fast paths.

Self-registers with the registry on import."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aa_auto_sdr.output._helpers import stringify_cell
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


class ExcelWriter:
    extension = ".xlsx"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)

        import pandas as pd

        sheets: dict[str, pd.DataFrame] = {
            "Summary": pd.DataFrame(
                [
                    ("RSID", doc.report_suite.rsid),
                    ("Name", doc.report_suite.name),
                    ("Timezone", doc.report_suite.timezone or ""),
                    ("Captured at", doc.captured_at.isoformat()),
                    ("Tool version", doc.tool_version),
                    ("Dimensions", len(doc.dimensions)),
                    ("Metrics", len(doc.metrics)),
                    ("Segments", len(doc.segments)),
                    ("Calculated Metrics", len(doc.calculated_metrics)),
                    ("Virtual Report Suites", len(doc.virtual_report_suites)),
                    ("Classifications", len(doc.classifications)),
                ],
                columns=["Field", "Value"],
            ),
            "Dimensions": _component_df([asdict(d) for d in doc.dimensions]),
            "Metrics": _component_df([asdict(m) for m in doc.metrics]),
            "Segments": _component_df([asdict(s) for s in doc.segments]),
            "Calculated Metrics": _component_df([asdict(c) for c in doc.calculated_metrics]),
            "Virtual Report Suites": _component_df([asdict(v) for v in doc.virtual_report_suites]),
            "Classifications": _component_df([asdict(c) for c in doc.classifications]),
        }

        target.parent.mkdir(parents=True, exist_ok=True)
        # strings_to_formulas/urls off: xlsxwriter otherwise converts any
        # leading-`=` string (user-authored component names) into a LIVE
        # formula cell, and URL-looking strings into hyperlinks.
        engine_kwargs = {"options": {"strings_to_formulas": False, "strings_to_urls": False}}
        with pd.ExcelWriter(target, engine="xlsxwriter", engine_kwargs=engine_kwargs) as xl:
            for name, df in sheets.items():
                df.to_excel(xl, sheet_name=name, index=False)
                ws = xl.sheets[name]
                ws.freeze_panes(1, 0)
                if df.shape[1] > 0 and df.shape[0] > 0:
                    ws.autofilter(0, 0, df.shape[0], df.shape[1] - 1)
                for col_idx, col in enumerate(df.columns):
                    # Component-sheet cells are already strings (stringify_cell);
                    # str() on the Summary sheet's mixed values matches what
                    # astype(str) produced, without a full column re-conversion.
                    longest = max((len(v) if isinstance(v, str) else len(str(v)) for v in df[col]), default=0)
                    width = max(len(str(col)), longest or 10)
                    ws.set_column(col_idx, col_idx, min(width + 2, 60))
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


def _component_df(rows: list[dict[str, Any]]):
    """Build a DataFrame for one component sheet, stringifying nested values."""
    import pandas as pd

    if not rows:
        return pd.DataFrame()
    flat = [{k: stringify_cell(v) for k, v in r.items()} for r in rows]
    return pd.DataFrame(flat)


register_writer("excel", ExcelWriter())
