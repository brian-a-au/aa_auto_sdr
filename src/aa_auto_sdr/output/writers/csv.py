"""CSV writer — one file per component type, UTF-8 with BOM, staged writes.

Self-registers with the registry on import. Returns one Path per file written:
summary, coverage, the 6 component types, and references (9 files), plus
quality_issues when a quality audit ran, then the `<stem>._manifest.json`
completion manifest last (10 or 11 paths). Files are staged and published together; see
`_publish_bundle`."""

from __future__ import annotations

import csv as _csv
import hashlib
import io
import json
import logging
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aa_auto_sdr.output._helpers import (
    component_headers,
    component_values,
    neutralize_formula,
    render_provenance_pairs,
    stringify_cell,
)
from aa_auto_sdr.output.coverage import (
    FAMILY_HEADINGS,
    QUALITY_ISSUE_COLUMNS,
    coverage_rows,
    quality_issue_cells,
    quality_status,
)
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)

# Completion manifest: `<stem>._manifest.json`, next to the section files.
CSV_MANIFEST_SUFFIX = "_manifest.json"
CSV_MANIFEST_VERSION = "1.0"


def _utcnow() -> datetime:
    """Manifest `generated_at` clock. A seam so sample outputs stay deterministic."""
    return datetime.now(UTC)


_COMPONENT_FIELDS: dict[str, str] = {
    "dimensions": "Dimension",
    "metrics": "Metric",
    "segments": "Segment",
    "calculated_metrics": "CalculatedMetric",
    "virtual_report_suites": "VirtualReportSuite",
    "classifications": "ClassificationDataset",
}


_QUALITY_ISSUE_HEADERS = QUALITY_ISSUE_COLUMNS


def _summary_rows(doc: SdrDocument) -> list[tuple[str, str]]:
    quality = quality_status(doc.quality)
    return [
        ("RSID", doc.report_suite.rsid),
        ("Name", doc.report_suite.name),
        ("Timezone", doc.report_suite.timezone or ""),
        ("Currency", doc.report_suite.currency or ""),
        ("Parent RSID", doc.report_suite.parent_rsid or ""),
        ("Captured at", doc.captured_at.isoformat()),
        ("Tool version", doc.tool_version),
        *render_provenance_pairs(doc),
        ("Dimensions", str(len(doc.dimensions))),
        ("Metrics", str(len(doc.metrics))),
        ("Segments", str(len(doc.segments))),
        ("Calculated Metrics", str(len(doc.calculated_metrics))),
        ("Virtual Report Suites", str(len(doc.virtual_report_suites))),
        ("Classifications", str(len(doc.classifications))),
        ("Quality verdict", (quality.verdict or "n/a") if quality.audited else "not run"),
        ("Quality policy threshold", quality.threshold or ""),
        ("Quality issues", str(quality.total) if quality.audited else ""),
    ]


def _coverage_csv_rows(doc: SdrDocument) -> list[list[str]]:
    return [[r.family, r.state.value, str(r.count), r.expansion_level or ""] for r in coverage_rows(doc)]


def _component_rows(field_name: str, items: list[Any]) -> tuple[list[str], list[list[str]]]:
    """Return (headers, rows) for one component family.

    Headers come from the model class, so an empty family still gets them,
    followed by the derived definition columns for segments and calculated
    metrics."""
    from aa_auto_sdr.api import models

    headers = component_headers(field_name, getattr(models, _COMPONENT_FIELDS[field_name]))
    rows = [[stringify_cell(v) for v in component_values(field_name, item)] for item in items]
    return headers, rows


def _encode_csv(headers: list[str], rows: list[list[str]]) -> str:
    """Format a CSV body as a string (suitable for atomic write).

    Data cells are formula-neutralized: component names are user-authored in
    AA, and Excel evaluates leading-`=` cells on CSV import."""
    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(headers)
    writer.writerows([neutralize_formula(cell) for cell in row] for row in rows)
    return buf.getvalue()


class CsvWriter:
    extension = ".csv"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        # Output filenames are derived from output_path. If the user passed
        # `out.csv`, we strip the .csv suffix and append `.<component>.csv` for
        # each file. If they passed `out` (no suffix), we use it as a stem.
        stem = output_path.stem if output_path.suffix == self.extension else output_path.name
        parent = output_path.parent

        paths = _publish_bundle(_sections(doc), parent=parent, stem=stem)

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "output_write format=csv output_path=%s count=%s duration_ms=%s",
            str(paths[0]),
            len(paths),
            duration_ms,
            extra={
                "format": "csv",
                "output_path": str(paths[0]),
                "count": len(paths),
                "duration_ms": duration_ms,
                "rsid": doc.report_suite.rsid,
            },
        )
        return paths


def _sections(doc: SdrDocument) -> list[tuple[str, str, list[str], list[list[str]]]]:
    """(file key, sheet name, headers, rows) for every file in the bundle, in order."""
    sections: list[tuple[str, str, list[str], list[list[str]]]] = [
        ("summary", "Summary", ["field", "value"], [list(r) for r in _summary_rows(doc)]),
        ("coverage", "Coverage", ["family", "state", "count", "expansion_level"], _coverage_csv_rows(doc)),
    ]
    for field_name, heading in FAMILY_HEADINGS.items():
        headers, rows = _component_rows(field_name, getattr(doc, field_name))
        sections.append((field_name, heading, headers, rows))
    # References appendix (always) — one row per reference edge
    from aa_auto_sdr.sdr.definitions import REFERENCE_COLUMNS, build_references, reference_rows

    reference_body = [list(r) for r in reference_rows(build_references(doc))]
    sections.append(("references", "References", list(REFERENCE_COLUMNS), reference_body))
    # Quality findings — only when an audit ran
    quality = quality_status(doc.quality)
    if quality.audited:
        issue_rows = [quality_issue_cells(i) for i in quality.issues]
        sections.append(("quality_issues", "Quality Issues", _QUALITY_ISSUE_HEADERS, issue_rows))
    return sections


def _publish_bundle(
    sections: list[tuple[str, str, list[str], list[list[str]]]],
    *,
    parent: Path,
    stem: str,
) -> list[Path]:
    """Stage every section, then publish them and the manifest last.

    Every file is rendered into a dot-prefixed staging directory next to the
    target first, so a failure while rendering leaves the published files
    untouched. The old manifest is removed before members are replaced and
    the new one is published last: a consumer that finds
    `<stem>._manifest.json` knows every file it lists was published by the
    same run. Replacing several files is not atomic as a set; a failure while
    publishing leaves no manifest. Files not in the new run are never deleted.
    The manifest is stem-scoped so several report suites can share a directory."""
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{stem}.csv-", dir=str(parent)))
    try:
        names: list[str] = []
        entries: list[dict[str, Any]] = []
        for key, sheet, headers, rows in sections:
            name = f"{stem}.{key}.csv"
            data = _encode_csv(headers, rows).encode("utf-8-sig")
            (staging / name).write_bytes(data)
            names.append(name)
            entries.append(
                {
                    "name": name,
                    "sheet": sheet,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "rows": len(rows),
                    "bytes": len(data),
                }
            )
        manifest_name = f"{stem}.{CSV_MANIFEST_SUFFIX}"
        manifest = {
            "manifest_version": CSV_MANIFEST_VERSION,
            "complete": True,
            "generated_at": _utcnow().isoformat(),
            "files": entries,
        }
        (staging / manifest_name).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        (parent / manifest_name).unlink(missing_ok=True)
        for name in names:
            os.replace(staging / name, parent / name)
        os.replace(staging / manifest_name, parent / manifest_name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return [parent / name for name in names] + [parent / manifest_name]


register_writer("csv", CsvWriter())
