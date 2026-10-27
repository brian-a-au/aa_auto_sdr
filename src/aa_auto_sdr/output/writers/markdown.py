"""Markdown writer — GFM-flavored, one section per component, pipe-escaped cells.

Self-registers with the registry on import. Returns a single Path."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aa_auto_sdr.api import models
from aa_auto_sdr.core.atomic_io import atomic_write_text
from aa_auto_sdr.output._helpers import (
    REFERENCE_HEADINGS,
    component_headers,
    component_values,
    escape_pipe,
    reference_display_rows,
    render_provenance_line,
    render_provenance_pairs,
    stringify_cell,
)
from aa_auto_sdr.output.coverage import (
    QUALITY_FINDING_HEADERS,
    CoverageRow,
    CoverageState,
    coverage_rows,
    quality_finding_rows,
    quality_status,
    quality_status_line,
)
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)

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
        *render_provenance_pairs(doc),
        ("Dimensions", str(len(doc.dimensions))),
        ("Metrics", str(len(doc.metrics))),
        ("Segments", str(len(doc.segments))),
        ("Calculated Metrics", str(len(doc.calculated_metrics))),
        ("Virtual Report Suites", str(len(doc.virtual_report_suites))),
        ("Classifications", str(len(doc.classifications))),
    ]
    body_rows = [[escape_pipe(k), escape_pipe(v)] for k, v in pairs]
    return _table(["Field", "Value"], body_rows)


def _coverage_table(rows: list[CoverageRow]) -> str:
    body = [
        [escape_pipe(r.heading), escape_pipe(r.label), str(r.count), escape_pipe(r.expansion_level or "")] for r in rows
    ]
    return _table(["Family", "State", "Count", "Expansion level"], body)


def _section(heading: str, attr: str, items: list[Any], cls_name: str, coverage: CoverageRow) -> str:
    if not items:
        return f"## {heading}\n\n_{escape_pipe(coverage.label)}_\n"
    headers = component_headers(attr, getattr(models, cls_name))
    rows = [[_cell(v) for v in component_values(attr, item)] for item in items]
    note = "" if coverage.state is CoverageState.COLLECTED else f"_{escape_pipe(coverage.label)}_\n\n"
    return f"## {heading}\n\n{note}{_table(headers, rows)}"


def _quality_parts(doc: SdrDocument) -> list[str]:
    """Status line, then a findings table when the audit produced any."""
    status = quality_status(doc.quality)
    parts = [f"{quality_status_line(status)}\n"]
    rows = quality_finding_rows(status)
    if rows:
        parts.append(_table(QUALITY_FINDING_HEADERS, [[_cell(c) for c in r] for r in rows]))
    return parts


def _render_note(doc: SdrDocument) -> list[str]:
    line = render_provenance_line(doc)
    return [] if line is None else [f"> {escape_pipe(line)}\n"]


def _document(doc: SdrDocument) -> str:
    rs = doc.report_suite
    coverage = coverage_rows(doc)
    parts = [
        f"# SDR — {rs.name} ({rs.rsid})\n",
        f"> Captured at {doc.captured_at.isoformat()} · tool version {doc.tool_version}\n",
        *_render_note(doc),
        "## Coverage\n",
        _coverage_table(coverage),
        "## Quality\n",
        *_quality_parts(doc),
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
    coverage_by_family = {r.family: r for r in coverage}
    for heading, attr, cls_name in _COMPONENT_SECTIONS:
        parts.append(_section(heading, attr, components_map[attr], cls_name, coverage_by_family[attr]))
    parts.append(_references_section(doc))
    return "\n".join(parts)


def _references_section(doc: SdrDocument) -> str:
    rows = reference_display_rows(doc)
    if not rows:
        return "## References\n\n_No references found._\n"
    body = [[escape_pipe(c) for c in r] for r in rows]
    return f"## References\n\n{_table(list(REFERENCE_HEADINGS), body)}"


class MarkdownWriter:
    extension = ".md"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, _document(doc), encoding="utf-8")
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "output_write format=markdown output_path=%s count=1 duration_ms=%s",
            str(target),
            duration_ms,
            extra={
                "format": "markdown",
                "output_path": str(target),
                "count": 1,
                "duration_ms": duration_ms,
                "rsid": doc.report_suite.rsid,
            },
        )
        return [target]


register_writer("markdown", MarkdownWriter())
