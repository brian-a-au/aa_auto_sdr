"""SdrDocument — the boundary type produced by builder and consumed by output/snapshot."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from aa_auto_sdr.api import models


@dataclass(frozen=True, slots=True)
class SdrDocument:
    """Boundary type produced by builder, consumed by output writers and snapshots.

    The `classifications` field carries `ClassificationDataset` instances —
    Adobe Analytics API 2.0 has no per-dimension classification list. Field name
    kept as `classifications` for user-facing familiarity in Excel sheet names."""

    report_suite: models.ReportSuite
    dimensions: list[models.Dimension]
    metrics: list[models.Metric]
    segments: list[models.Segment]
    calculated_metrics: list[models.CalculatedMetric]
    virtual_report_suites: list[models.VirtualReportSuite]
    classifications: list[models.ClassificationDataset]
    captured_at: datetime
    tool_version: str

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict shape used by JSON output and snapshots."""
        return {
            "report_suite": asdict(self.report_suite),
            "dimensions": [asdict(d) for d in self.dimensions],
            "metrics": [asdict(m) for m in self.metrics],
            "segments": [asdict(s) for s in self.segments],
            "calculated_metrics": [asdict(c) for c in self.calculated_metrics],
            "virtual_report_suites": [asdict(v) for v in self.virtual_report_suites],
            "classifications": [asdict(c) for c in self.classifications],
            "captured_at": self.captured_at.isoformat(),
            "tool_version": self.tool_version,
        }
