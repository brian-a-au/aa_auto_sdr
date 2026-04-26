"""HTML writer — single self-contained file with embedded CSS.

Self-registers with the registry on import. Returns a single Path."""

from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from aa_auto_sdr.api import models
from aa_auto_sdr.output._helpers import escape_html, stringify_cell
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

_CSS = """\
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  max-width: 1280px;
  margin: 2rem auto;
  padding: 0 1.5rem;
  color: #222;
  line-height: 1.4;
}
header { border-bottom: 1px solid #ddd; padding-bottom: 1rem; margin-bottom: 1.5rem; }
h1 { font-size: 1.5rem; margin: 0 0 0.25rem 0; }
.meta { color: #666; font-size: 0.9rem; margin: 0; }
section { margin: 2rem 0; }
h2 { font-size: 1.2rem; border-bottom: 1px solid #eee; padding-bottom: 0.25rem; }
h2 .count { color: #888; font-size: 0.9rem; font-weight: normal; margin-left: 0.5rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; vertical-align: top; }
th { position: sticky; top: 0; background: #fafafa; }
tbody tr:nth-child(even) { background: #fafafa; }
code { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 0.8rem;
       background: #f5f5f5; padding: 0.05rem 0.25rem; border-radius: 2px; }
td.long { max-width: 24rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
"""


_COMPONENT_SECTIONS: list[tuple[str, str, str]] = [
    # (heading, doc-attribute, model-class-name)
    ("Dimensions", "dimensions", "Dimension"),
    ("Metrics", "metrics", "Metric"),
    ("Segments", "segments", "Segment"),
    ("Calculated Metrics", "calculated_metrics", "CalculatedMetric"),
    ("Virtual Report Suites", "virtual_report_suites", "VirtualReportSuite"),
    ("Classifications", "classifications", "ClassificationDataset"),
]


def _summary_pairs(doc: SdrDocument) -> list[tuple[str, str]]:
    return [
        ("RSID", doc.report_suite.rsid),
        ("Name", doc.report_suite.name),
        ("Timezone", doc.report_suite.timezone or ""),
        ("Currency", doc.report_suite.currency or ""),
        ("Captured at", doc.captured_at.isoformat()),
        ("Tool version", doc.tool_version),
    ]


def _table_html(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape_html(h)}</th>" for h in headers)
    body_rows: list[str] = []
    for r in rows:
        cells = "".join(f'<td class="long" title="{escape_html(c)}">{escape_html(c)}</td>' for c in r)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _section_html(heading: str, items: list[Any], cls_name: str) -> str:
    cls = getattr(models, cls_name)
    headers = [f.name for f in fields(cls)]
    if not items:
        return f'<section><h2>{escape_html(heading)} <span class="count">0</span></h2><p><em>(none)</em></p></section>'
    rows = [[stringify_cell(asdict(item).get(h)) for h in headers] for item in items]
    return (
        f'<section><h2>{escape_html(heading)} <span class="count">{len(items)}</span></h2>'
        f"{_table_html(headers, rows)}</section>"
    )


def _summary_section_html(doc: SdrDocument) -> str:
    pairs = _summary_pairs(doc)
    rows = [[k, v] for k, v in pairs]
    return f"<section><h2>Summary</h2>{_table_html(['Field', 'Value'], rows)}</section>"


def _document_html(doc: SdrDocument) -> str:
    rs = doc.report_suite
    title = f"SDR — {rs.name} ({rs.rsid})"
    sections = [_summary_section_html(doc)]
    components_map: dict[str, list[Any]] = {
        "dimensions": doc.dimensions,
        "metrics": doc.metrics,
        "segments": doc.segments,
        "calculated_metrics": doc.calculated_metrics,
        "virtual_report_suites": doc.virtual_report_suites,
        "classifications": doc.classifications,
    }
    for heading, attr, cls_name in _COMPONENT_SECTIONS:
        sections.append(_section_html(heading, components_map[attr], cls_name))
    body_inner = (
        f"<header><h1>{escape_html(rs.name)}</h1>"
        f'<p class="meta">RSID <code>{escape_html(rs.rsid)}</code> · '
        f"captured {escape_html(doc.captured_at.isoformat())} · "
        f"tool {escape_html(doc.tool_version)}</p></header>" + "".join(sections)
    )
    return (
        f"<!doctype html>\n"
        f'<html lang="en">\n'
        f"  <head>\n"
        f'    <meta charset="utf-8">\n'
        f"    <title>{escape_html(title)}</title>\n"
        f"    <style>{_CSS}</style>\n"
        f"  </head>\n"
        f"  <body>{body_inner}</body>\n"
        f"</html>\n"
    )


class HtmlWriter:
    extension = ".html"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_document_html(doc), encoding="utf-8")
        return [target]


register_writer("html", HtmlWriter())
