"""SDK-agnostic normalized component models. Only `api/` produces these;
everything else consumes them. See design spec §2.

Field shapes were validated against real Adobe Analytics 2.0 API responses
via the spike at docs/superpowers/spikes/2026-04-25-aanalytics2-shape-spike.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReportSuite:
    """An Adobe Analytics report suite. `currency`, `timezone`, `parent_rsid`
    only populated when the fetcher passes `extended_info=True`."""

    rsid: str
    name: str
    timezone: str | None
    currency: str | None
    parent_rsid: str | None


@dataclass(frozen=True, slots=True)
class Dimension:
    """A dimension (eVar, prop, event, etc.).

    Real API 2.0 columns: category, id, name, parent, pathable, type.
    `description` and `tags` only populated when the fetcher passes
    `description=True, tags=True`."""

    id: str
    name: str
    type: str
    category: str | None
    parent: str
    pathable: bool
    description: str | None
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Metric:
    """A metric (numeric counter or rate).

    Real API 2.0 columns: category, id, name, precision, segmentable, type.
    `description`, `tags`, `data_group` only populated with the matching flags."""

    id: str
    name: str
    type: str
    category: str | None
    precision: int
    segmentable: bool
    description: str | None
    tags: list[str] = field(default_factory=list)
    data_group: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Segment:
    """A segment definition.

    `definition` is required for SDR fidelity — fetcher must pass
    `extended_info=True` (or use per-id `getSegment(id, full=True)`)."""

    id: str
    name: str
    description: str | None
    rsid: str
    owner_id: int | None
    definition: dict[str, Any]
    compatibility: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    created: str | None = None
    modified: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CalculatedMetric:
    """A calculated metric.

    Note: the API field is `definition`, not `formula`. We mirror the API name
    to avoid a translation layer. Fetcher must pass `extended_info=True`
    (or use per-id `getCalculatedMetric(id, full=True)`)."""

    id: str
    name: str
    description: str | None
    rsid: str
    owner_id: int | None
    polarity: str
    precision: int
    type: str
    definition: dict[str, Any]
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VirtualReportSuite:
    """A virtual report suite — a filtered view of a parent RS.

    Fetcher must pass `extended_info=True` to get parent_rsid, segment_list,
    curated_components, etc."""

    id: str
    name: str
    parent_rsid: str
    timezone: str | None
    description: str | None
    segment_list: list[str] = field(default_factory=list)
    curated_components: list[Any] = field(default_factory=list)
    modified: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClassificationDataset:
    """A classification dataset.

    Adobe Analytics API 2.0 has NO endpoint that lists classifications attached
    to a given dimension (this is a 1.4-only capability). The closest 2.0
    equivalent is `getClassificationDatasets(rsid)`, which returns datasets
    compatible with metrics in the report suite. We model what the API actually
    exposes — not the per-dimension classification view from CJA's mental model.

    See spike findings §4 for full discussion."""

    id: str
    name: str
    rsid: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReportSuiteSummary:
    """Lightweight RS summary for `--list-reportsuites`, `--stats`, `--interactive`.

    Distinct from `ReportSuite` (full schema with timezone/currency/parent_rsid).
    Carries only the fields CLI list views need."""

    rsid: str
    name: str | None
