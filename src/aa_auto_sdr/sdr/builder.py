"""Pure SDR builder: AaClient + RSID → SdrDocument.

NO I/O. Side effects belong elsewhere (output writers, snapshot store).
Component lists are sorted by ID for stable diffs.

`ComponentFilter` lets generation skip API calls for excluded types.
Filtered-out lists become empty in the document, and the document's
`collected_components` records which families were actually requested. An
empty list alone cannot tell "excluded" from "really empty", so anything that
compares captures must read the scope, not the arrays."""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, TypeVar

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.vrs_source import VrsSource
from aa_auto_sdr.sdr import quality as quality_module
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, FetchOutcomeMeta, SdrDocument
from aa_auto_sdr.sdr.quality import QualityRules, SeverityLevel

if TYPE_CHECKING:
    from aa_auto_sdr.api.cache import ValidationCache

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

    def collected(self) -> tuple[str, ...]:
        """Sorted family names this filter requests (the capture scope)."""
        return tuple(name for name in COMPONENT_FAMILIES if getattr(self, name))


_T = TypeVar("_T")

# `component_type` is a documented enumeration of singular names (see
# docs/LOGGING_STYLE.md), so a log query pinned to `component_type=dimension`
# has to match this record too.
_SINGULAR: dict[str, str] = {
    "dimensions": "dimension",
    "metrics": "metric",
    "segments": "segment",
    "calculated_metrics": "calculated_metric",
    "virtual_report_suites": "virtual_report_suite",
    "classifications": "classification",
}


def _sorted_unique(items: list[_T], *, family: str, rsid: str) -> list[_T]:
    """Sort a family by id and keep the first row per id.

    Every writer, snapshot, and diff keys a component by its id, so two rows
    sharing one id collapse onto the last during a comparison and quietly
    skew the unchanged count.

    This is the invariant guard, not the place a known repeat is handled: a
    response whose shape repeats an id is normalized in `api/fetch.py`, at
    the boundary the inspection commands read too, so their counts match the
    SDR built in the same run. Reaching the warning below means a family
    arrived with a repeat that its fetcher did not expect.

    Uniqueness is settled on the capture side rather than on read, because
    `--watch` reads back the snapshot it just wrote and the shared reader has
    to stay able to open a file an older release produced.
    """
    out: list[_T] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda i: i.id):  # type: ignore[attr-defined]
        if item.id in seen:  # type: ignore[attr-defined]
            continue
        seen.add(item.id)  # type: ignore[attr-defined]
        out.append(item)
    dropped = len(items) - len(out)
    if dropped:
        logger.warning(
            "duplicate_component_ids rsid=%s component_type=%s count=%s; keeping the first row per id",
            rsid,
            _SINGULAR[family],
            dropped,
            extra={"rsid": rsid, "component_type": _SINGULAR[family], "count": dropped},
        )
    return out


def build_sdr(
    client: AaClient,
    rsid: str,
    *,
    captured_at: datetime,
    tool_version: str,
    component_filter: ComponentFilter | None = None,
    audit_naming: bool = False,  # NEW (v1.9.0)
    flag_stale: bool = False,  # NEW (v1.9.0)
    fail_on_quality: SeverityLevel | None = None,  # NEW (v1.12.0)
    cache: ValidationCache | None = None,  # NEW (v1.12.0)
    quality_rules: QualityRules | None = None,
    vrs_source: VrsSource | None = None,
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

    # Graceful-degrade fetchers return FetchOutcome; bubbling fetchers return list[T].
    # Only collect fetch_status entries for non-healthy outcomes from the two
    # graceful-degrade fetchers (VRS, classifications). Filtered-out types skip
    # the fetch entirely and do not appear in fetch_status.
    fetch_status: dict[str, FetchOutcomeMeta] = {}

    if flt.virtual_report_suites:
        vrs_outcome = fetch.fetch_virtual_report_suites(client, rsid, source=vrs_source)
        if vrs_outcome.status != "healthy":
            fetch_status["virtual_report_suites"] = FetchOutcomeMeta(
                status=vrs_outcome.status,
                expansion_level=vrs_outcome.expansion_level,
            )
        vrs_data = vrs_outcome.data
    else:
        vrs_data = []

    if flt.classifications:
        classifications_outcome = fetch.fetch_classification_datasets(client, rsid)
        if classifications_outcome.status != "healthy":
            fetch_status["classifications"] = FetchOutcomeMeta(
                status=classifications_outcome.status,
                expansion_level=classifications_outcome.expansion_level,
            )
        classifications_data = classifications_outcome.data
    else:
        classifications_data = []

    doc = SdrDocument(
        report_suite=rs,
        dimensions=_sorted_unique(
            fetch.fetch_dimensions(client, rsid) if flt.dimensions else [],
            family="dimensions",
            rsid=rsid,
        ),
        metrics=_sorted_unique(
            fetch.fetch_metrics(client, rsid) if flt.metrics else [],
            family="metrics",
            rsid=rsid,
        ),
        segments=_sorted_unique(
            fetch.fetch_segments(client, rsid) if flt.segments else [],
            family="segments",
            rsid=rsid,
        ),
        calculated_metrics=_sorted_unique(
            fetch.fetch_calculated_metrics(client, rsid) if flt.calculated_metrics else [],
            family="calculated_metrics",
            rsid=rsid,
        ),
        virtual_report_suites=_sorted_unique(vrs_data, family="virtual_report_suites", rsid=rsid),
        classifications=_sorted_unique(classifications_data, family="classifications", rsid=rsid),
        captured_at=captured_at,
        tool_version=tool_version,
        fetch_status=fetch_status,
        collected_components=flt.collected(),
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

    # v1.9.0 quality pass + v1.12.0 severity engine (post-build, pure —
    # no I/O, no API calls). Composes audit_naming + detect_stale into
    # the v1.12.0 quality block shape (with `issues` + `summary`).
    if audit_naming or flag_stale:
        quality = quality_module.run_audits(
            doc,
            audit_naming_enabled=audit_naming,
            flag_stale_enabled=flag_stale,
            fail_on_quality=fail_on_quality,
            cache=cache,
            rsid=rsid,
            rules=quality_rules,
        )
        doc = dataclasses.replace(doc, quality=quality)

    return doc
