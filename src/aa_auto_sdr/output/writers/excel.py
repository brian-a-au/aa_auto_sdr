"""Excel writer — multi-sheet workbook, frozen header row, autofilter on every sheet.

Heavy imports (pandas, xlsxwriter) are deferred to method scope so the registry
can be loaded without paying the import cost on fast paths.

Self-registers with the registry on import."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from aa_auto_sdr.output._helpers import stringify_cell
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument


class ExcelWriter:
    extension = ".xlsx"

    def write(self, doc: SdrDocument, output_path: Path) -> Path:
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
        with pd.ExcelWriter(target, engine="xlsxwriter") as xl:
            for name, df in sheets.items():
                df.to_excel(xl, sheet_name=name, index=False)
                ws = xl.sheets[name]
                ws.freeze_panes(1, 0)
                if df.shape[1] > 0 and df.shape[0] > 0:
                    ws.autofilter(0, 0, df.shape[0], df.shape[1] - 1)
                for col_idx, col in enumerate(df.columns):
                    width = max(len(str(col)), int(df[col].astype(str).str.len().max() or 10))
                    ws.set_column(col_idx, col_idx, min(width + 2, 60))
        return target


def _component_df(rows: list[dict[str, Any]]):
    """Build a DataFrame for one component sheet, stringifying nested values."""
    import pandas as pd

    if not rows:
        return pd.DataFrame()
    flat = [{k: stringify_cell(v) for k, v in r.items()} for r in rows]
    return pd.DataFrame(flat)


register_writer("excel", ExcelWriter())
