"""Template-fill Excel writer (v1.16.0).

Opens an existing Adobe BRD/SDR `.xlsx` template, locates each data sheet by
name + section anchor, finds the header row by content, and fills component
data into the rows below. Preserves styles, cross-sheet formulas, defined
names, column widths, page setup, and every cell not explicitly written.

Heavy import (`openpyxl`) is deferred to method scope so the registry can be
bootstrapped on fast paths without paying the import cost. Mirrors the
deferred-pandas pattern in `excel.py`.

Self-registers under the `excel-template` format key on import.

Read-only AA 2.0 invariant: `openpyxl` writes target local `.xlsx` files only,
never the Adobe Analytics API."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


class ExcelTemplateWriter:
    extension = ".xlsx"

    def __init__(self) -> None:
        self.template_path: Path | None = None
        self.organization: str | None = None

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

        # Subsequent tasks add: _fill_glossary_org, _fill_dimensions,
        # _fill_metrics, _fill_metrics_segments.

        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)

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


register_writer("excel-template", ExcelTemplateWriter())
