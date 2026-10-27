"""SdrDocument — the boundary type produced by builder and consumed by output/snapshot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from aa_auto_sdr.api import models

# Component families a capture can collect, sorted. The report suite itself is
# always collected and is not a family.
COMPONENT_FAMILIES: tuple[str, ...] = (
    "calculated_metrics",
    "classifications",
    "dimensions",
    "metrics",
    "segments",
    "virtual_report_suites",
)


@dataclass(frozen=True, slots=True)
class FetchOutcomeMeta:
    """Per-component-type fetch-status record persisted on SdrDocument.

    Populated only for non-`healthy` outcomes; healthy fetches are absent
    from `SdrDocument.fetch_status` rather than mapped to "healthy". See
    spec §4.3.
    """

    status: models.FetchStatus
    expansion_level: str | None


@dataclass(frozen=True, slots=True)
class RenderProvenance:
    """When and by which tool version a saved capture was re-rendered.

    Set only on documents rebuilt by `--render-from`. The capture's own
    `captured_at` / `tool_version` are kept unchanged on the document; this
    records the separate render step."""

    rendered_at: datetime
    tool_version: str


@dataclass(frozen=True, slots=True)
class SdrDocument:
    """Boundary type produced by builder, consumed by output writers and snapshots.

    The `classifications` field carries `ClassificationDataset` instances —
    Adobe Analytics API 2.0 has no per-dimension classification list. Field name
    kept as `classifications` for user-facing familiarity in Excel sheet names.

    `fetch_status` (v1.7.1+) is keyed by the plural envelope-component name
    (`"virtual_report_suites"`, `"classifications"`) and only populated for
    non-`healthy` outcomes. Healthy fetches omit the key entirely.

    `collected_components` is the sorted tuple of families that were requested
    and fetched (capture scope), independent of fetch health: a degraded family
    is still collected. `None` means scope is unknown, which only legacy inputs
    produce; the builder always sets it from its `ComponentFilter`.

    `rendered` is None for a live capture. `--render-from` sets it, and
    `to_dict()` then adds `rendered_at` / `rendered_by_tool_version`; a live
    capture's dict never carries those keys."""

    report_suite: models.ReportSuite
    dimensions: list[models.Dimension]
    metrics: list[models.Metric]
    segments: list[models.Segment]
    calculated_metrics: list[models.CalculatedMetric]
    virtual_report_suites: list[models.VirtualReportSuite]
    classifications: list[models.ClassificationDataset]
    captured_at: datetime
    tool_version: str
    fetch_status: dict[str, FetchOutcomeMeta] = field(default_factory=dict)
    quality: dict[str, Any] | None = None  # NEW (v1.9.0): None when no audit ran
    # Defaults to unknown so a constructor that omits scope can never claim a
    # full capture; build_sdr always passes it explicitly.
    collected_components: tuple[str, ...] | None = None
    rendered: RenderProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict shape used by JSON output and snapshots.

        Includes `quality` (None when no audit ran) and `fetch_status`
        (FetchOutcomeMeta entries unpacked via asdict). Bundled v1.12.0
        correctness fix; pre-v1.12.0 builds silently dropped these.
        """
        payload: dict[str, Any] = {
            "report_suite": asdict(self.report_suite),
            "dimensions": [asdict(d) for d in self.dimensions],
            "metrics": [asdict(m) for m in self.metrics],
            "segments": [asdict(s) for s in self.segments],
            "calculated_metrics": [asdict(c) for c in self.calculated_metrics],
            "virtual_report_suites": [asdict(v) for v in self.virtual_report_suites],
            "classifications": [asdict(c) for c in self.classifications],
            "captured_at": self.captured_at.isoformat(),
            "tool_version": self.tool_version,
            "fetch_status": {ctype: asdict(meta) for ctype, meta in self.fetch_status.items()},
            "quality": self.quality,
            "collected_components": (
                sorted(self.collected_components) if self.collected_components is not None else None
            ),
        }
        if self.rendered is not None:
            payload["rendered_at"] = self.rendered.rendered_at.isoformat()
            payload["rendered_by_tool_version"] = self.rendered.tool_version
        return payload
