"""CSV writer — one file per component type, UTF-8 with BOM, atomic writes.

Self-registers with the registry on import. Returns one Path per file written
(7 paths per SdrDocument: summary + 6 component types)."""

from __future__ import annotations

import csv as _csv
import io
import os
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from aa_auto_sdr.output._helpers import stringify_cell
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

_COMPONENT_FIELDS: dict[str, str] = {
    "dimensions": "Dimension",
    "metrics": "Metric",
    "segments": "Segment",
    "calculated_metrics": "CalculatedMetric",
    "virtual_report_suites": "VirtualReportSuite",
    "classifications": "ClassificationDataset",
}


def _atomic_write_text(path: Path, content: str, *, encoding: str) -> None:
    """Write `content` to `path` atomically. Used by csv writer (and reusable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _summary_rows(doc: SdrDocument) -> list[tuple[str, str]]:
    return [
        ("RSID", doc.report_suite.rsid),
        ("Name", doc.report_suite.name),
        ("Timezone", doc.report_suite.timezone or ""),
        ("Currency", doc.report_suite.currency or ""),
        ("Parent RSID", doc.report_suite.parent_rsid or ""),
        ("Captured at", doc.captured_at.isoformat()),
        ("Tool version", doc.tool_version),
        ("Dimensions", str(len(doc.dimensions))),
        ("Metrics", str(len(doc.metrics))),
        ("Segments", str(len(doc.segments))),
        ("Calculated Metrics", str(len(doc.calculated_metrics))),
        ("Virtual Report Suites", str(len(doc.virtual_report_suites))),
        ("Classifications", str(len(doc.classifications))),
    ]


def _component_rows(items: list[Any]) -> tuple[list[str], list[list[str]]]:
    """Return (headers, rows) for a list of frozen dataclass instances."""
    if not items:
        return [], []
    cls = type(items[0])
    headers = [f.name for f in fields(cls)]
    rows = [[stringify_cell(asdict(item).get(h)) for h in headers] for item in items]
    return headers, rows


def _component_headers_for_empty(field_name: str) -> list[str]:
    """When a component list is empty, we can't derive headers from the data,
    so use the dataclass field names directly."""
    from aa_auto_sdr.api import models

    cls = getattr(models, _COMPONENT_FIELDS[field_name])
    return [f.name for f in fields(cls)]


def _encode_csv(headers: list[str], rows: list[list[str]]) -> str:
    """Format a CSV body as a string (suitable for atomic write)."""
    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue()


class CsvWriter:
    extension = ".csv"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        # Output filenames are derived from output_path. If the user passed
        # `out.csv`, we strip the .csv suffix and append `.<component>.csv` for
        # each file. If they passed `out` (no suffix), we use it as a stem.
        stem = output_path.stem if output_path.suffix == self.extension else output_path.name
        parent = output_path.parent

        paths: list[Path] = []

        # Summary
        summary_path = parent / f"{stem}.summary.csv"
        summary_body = _encode_csv(["field", "value"], [list(r) for r in _summary_rows(doc)])
        _atomic_write_text(summary_path, summary_body, encoding="utf-8-sig")
        paths.append(summary_path)

        # Component lists
        component_attr_map = {
            "dimensions": doc.dimensions,
            "metrics": doc.metrics,
            "segments": doc.segments,
            "calculated_metrics": doc.calculated_metrics,
            "virtual_report_suites": doc.virtual_report_suites,
            "classifications": doc.classifications,
        }

        for field_name, items in component_attr_map.items():
            file_path = parent / f"{stem}.{field_name}.csv"
            if items:
                headers, rows = _component_rows(items)
            else:
                headers = _component_headers_for_empty(field_name)
                rows = []
            body = _encode_csv(headers, rows)
            _atomic_write_text(file_path, body, encoding="utf-8-sig")
            paths.append(file_path)

        return paths


register_writer("csv", CsvWriter())
