"""Markdown writer — GFM-flavored, one section per component, pipe-escaped cells.

Self-registers with the registry on import. Returns a single Path."""

from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from aa_auto_sdr.api import models
from aa_auto_sdr.output._helpers import escape_pipe, stringify_cell
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

_COMPONENT_SECTIONS: list[tuple[str, str, str]] = [
    # (heading, doc-attribute, model-class-name)
    ("Dimensions", "dimensions", "Dimension"),
    ("Metrics", "metrics", "Metric"),
    ("Segments", "segments", "Segment"),
    ("Calculated Metrics", "calculated_metrics", "CalculatedMetric"),
    ("Virtual Report Suites", "virtual_report_suites", "VirtualReportSuite"),
    ("Classifications", "classifications", "ClassificationDataset"),
]


def _cell(value: Any) -> str:
    """Stringify a value and escape it for a GFM table cell."""
    s = stringify_cell(value)
    if isinstance(value, (dict, list)):
        # Wrap nested JSON in backticks so it renders as inline code in tables.
        # Pipes inside JSON still need escaping.
        return f"`{escape_pipe(s)}`"
    return escape_pipe(s)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
    return f"{head}\n{sep}\n{body}\n" if rows else f"{head}\n{sep}\n"


def _summary_table(doc: SdrDocument) -> str:
    pairs = [
        ("RSID", doc.report_suite.rsid),
        ("Name", doc.report_suite.name),
        ("Timezone", doc.report_suite.timezone or ""),
        ("Currency", doc.report_suite.currency or ""),
        ("Captured at", doc.captured_at.isoformat()),
        ("Tool version", doc.tool_version),
        ("Dimensions", str(len(doc.dimensions))),
        ("Metrics", str(len(doc.metrics))),
        ("Segments", str(len(doc.segments))),
        ("Calculated Metrics", str(len(doc.calculated_metrics))),
        ("Virtual Report Suites", str(len(doc.virtual_report_suites))),
        ("Classifications", str(len(doc.classifications))),
    ]
    body_rows = [[escape_pipe(k), escape_pipe(v)] for k, v in pairs]
    return _table(["Field", "Value"], body_rows)


def _section(heading: str, items: list[Any], cls_name: str) -> str:
    if not items:
        return f"## {heading}\n\n_(none)_\n"
    cls = getattr(models, cls_name)
    headers = [f.name for f in fields(cls)]
    rows = []
    for item in items:
        d = asdict(item)
        rows.append([_cell(d.get(h)) for h in headers])
    return f"## {heading}\n\n{_table(headers, rows)}"


def _document(doc: SdrDocument) -> str:
    rs = doc.report_suite
    parts = [
        f"# SDR — {rs.name} ({rs.rsid})\n",
        f"> Captured at {doc.captured_at.isoformat()} · tool version {doc.tool_version}\n",
        "## Summary\n",
        _summary_table(doc),
    ]
    components_map = {
        "dimensions": doc.dimensions,
        "metrics": doc.metrics,
        "segments": doc.segments,
        "calculated_metrics": doc.calculated_metrics,
        "virtual_report_suites": doc.virtual_report_suites,
        "classifications": doc.classifications,
    }
    for heading, attr, cls_name in _COMPONENT_SECTIONS:
        parts.append(_section(heading, components_map[attr], cls_name))
    return "\n".join(parts)


class MarkdownWriter:
    extension = ".md"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_document(doc), encoding="utf-8")
        return [target]


register_writer("markdown", MarkdownWriter())
