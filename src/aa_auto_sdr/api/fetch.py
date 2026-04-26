"""Per-component fetchers. Calls into the aanalytics2 SDK and normalizes
results into our SDK-agnostic dataclasses (api/models.py).

Two non-obvious facts (validated by the spike at
docs/superpowers/spikes/2026-04-25-aanalytics2-shape-spike.md):

1. The SDK returns pandas DataFrames, not lists of dicts. We coerce at the
   boundary via `.to_dict(orient='records')`.

2. Default columns are sparse. We pass richer-info flags so we get all the
   fields the SDR cares about:
     - dimensions: description=True, tags=True
     - metrics:    description=True, tags=True, dataGroup=True
     - segments / calc metrics / VRS: extended_info=True (carries `definition`)

Classifications are fetched via getClassificationDatasets(rsid) — the only
API 2.0 list endpoint. The wrapper has no per-dimension classifications
method because the underlying API has none.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from aa_auto_sdr.api import models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError


def _records(value: Any) -> list[dict[str, Any]]:
    """Coerce a DataFrame (or a plain list) into a list of dicts."""
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _str_or_none(d: dict[str, Any], key: str) -> str | None:
    val = d.get(key)
    if val is None:
        return None
    text = str(val)
    return text if text and text.strip() else None


def _bool(d: dict[str, Any], key: str, default: bool = False) -> bool:
    val = d.get(key)
    return bool(val) if val is not None else default


def _int(d: dict[str, Any], key: str, default: int = 0) -> int:
    val = d.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except TypeError, ValueError:
        return default


def _list(d: dict[str, Any], key: str) -> list[Any]:
    val = d.get(key)
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _owner_id(raw: dict[str, Any]) -> int | None:
    owner = raw.get("owner")
    if isinstance(owner, dict):
        return _int(owner, "id") or None
    return None


def _extra(d: dict[str, Any], known: set[str]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in known}


def fetch_report_suite(client: AaClient, rsid: str) -> models.ReportSuite:
    """Find the report suite with the given rsid. Uses extended_info to get
    currency / parentRsid / timezone fields."""
    suites = _records(client.handle.getReportSuites(extended_info=True))
    for raw in suites:
        if raw.get("rsid") == rsid:
            return models.ReportSuite(
                rsid=str(raw["rsid"]),
                name=str(raw.get("name", rsid)),
                timezone=_str_or_none(raw, "timezone") or _str_or_none(raw, "timezoneZoneinfo"),
                currency=_str_or_none(raw, "currency"),
                parent_rsid=_str_or_none(raw, "parentRsid"),
            )
    raise ReportSuiteNotFoundError(f"Report suite '{rsid}' not found")


def fetch_dimensions(client: AaClient, rsid: str) -> list[models.Dimension]:
    raws = _records(
        client.handle.getDimensions(rsid=rsid, description=True, tags=True),
    )
    known = {"id", "name", "type", "category", "parent", "pathable", "description", "tags"}
    return [
        models.Dimension(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            type=str(r.get("type", "unknown")),
            category=_str_or_none(r, "category"),
            parent=str(r.get("parent") or ""),
            pathable=_bool(r, "pathable"),
            description=_str_or_none(r, "description"),
            tags=_list(r, "tags"),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_metrics(client: AaClient, rsid: str) -> list[models.Metric]:
    # NOTE: `dataGroup=True` removed in v0.1.1. The aanalytics2 wrapper internally
    # slices the response DataFrame to a hardcoded column list that includes
    # `dataGroup` — but the API doesn't always return that column for every RS,
    # which raises `KeyError: "['dataGroup'] not in index"`. Until upstream fixes
    # the slice or we figure out which RS shapes are safe, we skip the flag and
    # leave `data_group` as None on the Metric model.
    raws = _records(
        client.handle.getMetrics(rsid=rsid, description=True, tags=True),
    )
    known = {
        "id",
        "name",
        "type",
        "category",
        "precision",
        "segmentable",
        "description",
        "tags",
        "dataGroup",
    }
    return [
        models.Metric(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            type=str(r.get("type", "unknown")),
            category=_str_or_none(r, "category"),
            precision=_int(r, "precision"),
            segmentable=_bool(r, "segmentable"),
            description=_str_or_none(r, "description"),
            tags=_list(r, "tags"),
            data_group=_str_or_none(r, "dataGroup"),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_segments(client: AaClient, rsid: str) -> list[models.Segment]:
    """Pulls segments for the rsid, with extended_info for the `definition` body."""
    raws = _records(
        client.handle.getSegments(rsids_list=[rsid], extended_info=True),
    )
    known = {
        "id",
        "name",
        "description",
        "rsid",
        "owner",
        "definition",
        "compatibility",
        "tags",
        "created",
        "modified",
    }
    return [
        models.Segment(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            description=_str_or_none(r, "description"),
            rsid=str(r.get("rsid", rsid)),
            owner_id=_owner_id(r),
            definition=dict(r.get("definition") or {}),
            compatibility=dict(r.get("compatibility") or {}),
            tags=_list(r, "tags"),
            created=_str_or_none(r, "created"),
            modified=_str_or_none(r, "modified"),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_calculated_metrics(
    client: AaClient,
    rsid: str,
) -> list[models.CalculatedMetric]:
    """Pulls calculated metrics for the rsid, with extended_info for `definition`."""
    raws = _records(
        client.handle.getCalculatedMetrics(rsids_list=[rsid], extended_info=True),
    )
    known = {
        "id",
        "name",
        "description",
        "rsid",
        "owner",
        "polarity",
        "precision",
        "type",
        "definition",
        "tags",
        "categories",
    }
    return [
        models.CalculatedMetric(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            description=_str_or_none(r, "description"),
            rsid=str(r.get("rsid", rsid)),
            owner_id=_owner_id(r),
            polarity=str(r.get("polarity", "positive")),
            precision=_int(r, "precision"),
            type=str(r.get("type", "decimal")),
            definition=dict(r.get("definition") or {}),
            tags=_list(r, "tags"),
            categories=_list(r, "categories"),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_virtual_report_suites(
    client: AaClient,
    parent_rsid: str,
) -> list[models.VirtualReportSuite]:
    """Lists VRS visible to the org, filtered to those whose parent matches.

    The SDK call has no rsid filter — we filter client-side after pulling all
    VRS via extended_info=True (which gives us `parentRsid`)."""
    raws = _records(client.handle.getVirtualReportSuites(extended_info=True))
    known = {
        "id",
        "name",
        "parentRsid",
        "timezone",
        "timezoneZoneinfo",
        "description",
        "segmentList",
        "curatedComponents",
        "modified",
    }
    return [
        models.VirtualReportSuite(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            parent_rsid=str(r.get("parentRsid", "")),
            timezone=_str_or_none(r, "timezone") or _str_or_none(r, "timezoneZoneinfo"),
            description=_str_or_none(r, "description"),
            segment_list=_list(r, "segmentList"),
            curated_components=_list(r, "curatedComponents"),
            modified=_str_or_none(r, "modified"),
            extra=_extra(r, known),
        )
        for r in raws
        if r.get("parentRsid") == parent_rsid
    ]


_CLASSIFICATION_ID_KEYS = ("id", "dataSetId", "datasetId", "data_set_id")
_CLASSIFICATION_NAME_KEYS = ("name", "displayName", "display_name")


def _first_present(d: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def fetch_classification_datasets(
    client: AaClient,
    rsid: str,
) -> list[models.ClassificationDataset]:
    """Lists classification datasets compatible with metrics in the report suite.

    This is the only enumeration path Adobe Analytics API 2.0 exposes for
    classifications — there is no per-dimension list endpoint.

    The endpoint's response shape varies by org/RS. We tolerate `id` /
    `dataSetId` / `datasetId` for the identifier, and `name` / `displayName`
    for the human-readable name. Records missing both id-like keys are skipped.
    Any failure of the underlying call returns an empty list rather than
    breaking the whole SDR — classifications are best-effort in v0.1.x."""
    try:
        raws = _records(client.handle.getClassificationDatasets(rsid=rsid))
    except Exception as e:  # wrapper raises various exception types
        import sys

        print(
            f"warning: classifications fetch failed ({type(e).__name__}: {e}); skipping",
            file=sys.stderr,
            flush=True,
        )
        return []

    known = {*_CLASSIFICATION_ID_KEYS, *_CLASSIFICATION_NAME_KEYS, "rsid"}
    out: list[models.ClassificationDataset] = []
    for r in raws:
        ds_id = _first_present(r, _CLASSIFICATION_ID_KEYS)
        if ds_id is None:
            continue
        ds_name = _first_present(r, _CLASSIFICATION_NAME_KEYS) or ds_id
        out.append(
            models.ClassificationDataset(
                id=ds_id,
                name=ds_name,
                rsid=str(r.get("rsid", rsid)),
                extra=_extra(r, known),
            ),
        )
    return out
