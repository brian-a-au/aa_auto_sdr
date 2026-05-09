"""Pure SDR builder: AaClient + RSID → SdrDocument.

NO I/O. Side effects belong elsewhere (output writers, snapshot store).
Component lists are sorted by ID for stable diffs.

v1.2 — `ComponentFilter` lets generation skip API calls for excluded types.
Filtered-out lists become empty in the document; snapshot envelopes always
carry the full schema (with empty arrays for filtered types) so diffs across
runs with different filters remain meaningful."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ComponentFilter:
    """Selects which component types to fetch + render. All True by default."""

    metrics: bool = True
    dimensions: bool = True
    segments: bool = True
    calculated_metrics: bool = True
    virtual_report_suites: bool = True
    classifications: bool = True

    @classmethod
    def from_args(
        cls,
        *,
        metrics_only: bool = False,
        dimensions_only: bool = False,
    ) -> ComponentFilter:
        if metrics_only and dimensions_only:
            # Caller's job to enforce mutex; defensive default = include all.
            return cls()
        if metrics_only:
            return cls(
                metrics=True,
                dimensions=False,
                segments=False,
                calculated_metrics=False,
                virtual_report_suites=False,
                classifications=False,
            )
        if dimensions_only:
            return cls(
                metrics=False,
                dimensions=True,
                segments=False,
                calculated_metrics=False,
                virtual_report_suites=False,
                classifications=False,
            )
        return cls()


def build_sdr(
    client: AaClient,
    rsid: str,
    *,
    captured_at: datetime,
    tool_version: str,
    component_filter: ComponentFilter | None = None,
) -> SdrDocument:
    """Fetch components for `rsid` (per `component_filter`) and assemble an SdrDocument."""
    flt = component_filter or ComponentFilter()
    started = time.monotonic()
    logger.debug(
        "build_sdr starting rsid=%s tool_version=%s",
        rsid,
        tool_version,
        extra={"rsid": rsid, "tool_version": tool_version},
    )
    rs = fetch.fetch_report_suite(client, rsid)
    doc = SdrDocument(
        report_suite=rs,
        dimensions=sorted(
            fetch.fetch_dimensions(client, rsid) if flt.dimensions else [],
            key=lambda d: d.id,
        ),
        metrics=sorted(
            fetch.fetch_metrics(client, rsid) if flt.metrics else [],
            key=lambda m: m.id,
        ),
        segments=sorted(
            fetch.fetch_segments(client, rsid) if flt.segments else [],
            key=lambda s: s.id,
        ),
        calculated_metrics=sorted(
            fetch.fetch_calculated_metrics(client, rsid) if flt.calculated_metrics else [],
            key=lambda c: c.id,
        ),
        virtual_report_suites=sorted(
            fetch.fetch_virtual_report_suites(client, rsid).data if flt.virtual_report_suites else [],
            key=lambda v: v.id,
        ),
        classifications=sorted(
            fetch.fetch_classification_datasets(client, rsid).data if flt.classifications else [],
            key=lambda c: c.id,
        ),
        captured_at=captured_at,
        tool_version=tool_version,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    component_count = (
        len(doc.dimensions)
        + len(doc.metrics)
        + len(doc.segments)
        + len(doc.calculated_metrics)
        + len(doc.virtual_report_suites)
        + len(doc.classifications)
    )
    logger.debug(
        "build_sdr complete rsid=%s count=%s duration_ms=%s",
        rsid,
        component_count,
        duration_ms,
        extra={"rsid": rsid, "count": component_count, "duration_ms": duration_ms},
    )
    return doc
