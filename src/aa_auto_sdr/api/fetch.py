"""Per-component fetchers. Calls into the aanalytics2 SDK and normalizes
results into our SDK-agnostic dataclasses (api/models.py).

Dimensions and metrics use supported raw SDK responses (aanalytics2 >=0.5.4)
to preserve tags and metadata omitted by the default DataFrame column selection.
Other DataFrame responses are normalized at the boundary. Segments, calculated
metrics, and VRS request extended information for their definitions.

Classifications are fetched via getClassificationDatasets(rsid) — the only
API 2.0 list endpoint. The wrapper has no per-dimension classifications
method because the underlying API has none.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any, Literal, TypeVar

import pandas as pd

from aa_auto_sdr.api import models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.report_suite_index import ReportSuiteIndex
from aa_auto_sdr.api.resilience import (
    RetryPolicy,
    classify_permanent_vrs_shape_error,
    classify_transient_sdk_call,
    log_retry_attempt,
    with_retries,
)
from aa_auto_sdr.api.vrs_source import VrsRows, VrsSource
from aa_auto_sdr.core.exceptions import (
    AmbiguousMatchError,
    ApiError,
    ReportSuiteNotFoundError,
    TransientApiError,
    VrsEndpointShapeError,
)

NameMatchStrategy = Literal["exact", "insensitive", "fuzzy"]
_NAME_MATCH_VALUES: tuple[str, ...] = ("exact", "insensitive", "fuzzy")
_FUZZY_THRESHOLD = 0.85

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _retry_and_normalize(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy,
    rsid: str | None = None,
    component_type: str | None = None,
) -> T:
    """Run `fn` under `policy`, classifying SDK-shape failures as transient.

    Two responsibilities:

    1. Inner classifier (via classify_transient_sdk_call) — translates the SDK's
       heterogeneous failure shapes into our TransientApiError so with_retries/
       is_retryable can dispatch on a typed signal.
    2. Outer normalizer — any non-ApiError exception that escapes with_retries
       (genuine bugs: AttributeError, TypeError; or unexpected SDK shapes) is
       wrapped as plain ApiError so the CLI's existing except-ApiError catches
       translate to ExitCode.API (12) without exposing internal exception types.
       TransientApiError (subclass of ApiError) and plain ApiError pass through.

    Used by bubbling fetchers (dimensions, metrics, segments, calc-metrics,
    report-suite, report-suite-summaries, resolve_rsid). Graceful-degrade
    fetchers (VRS ladder, classifications, VRS-summary discovery) call
    with_retries directly inside their existing try/except envelopes because
    they need to inspect the underlying exception type to decide between
    fallback rungs / [] / ApiError-normalization.
    """
    try:
        return with_retries(
            lambda: classify_transient_sdk_call(fn, component_type=component_type),
            policy=policy,
            on_attempt=lambda a, m, d, e: log_retry_attempt(
                a,
                m,
                d,
                e,
                rsid=rsid,
                component_type=component_type,
            ),
        )
    except ApiError:
        raise  # TransientApiError or plain ApiError — both pass through
    except Exception as e:
        # Defensive: AttributeError / TypeError / etc. — non-transient bugs
        # that the inner classifier doesn't catch.
        ctx = f"{component_type} " if component_type else ""
        raise ApiError(f"{ctx}fetch failed: {type(e).__name__}: {e}") from e


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


def _response_rows(value: Any, *, rsid: str, component_type: str) -> list[Any]:
    """Coerce a component-list response to rows, rejecting non-list shapes.

    Keeps DataFrame compatibility at the existing boundary, but never
    interprets an error mapping or an unexpected response shape as empty
    success.
    """
    # Connector discards HTTP status. Before raw mode these known error stubs
    # raised pandas ValueError and were retried. Preserve that ambiguity/budget,
    # without treating arbitrary malformed lists or mappings as transient.
    if isinstance(value, dict) and "id" not in value:
        error = value.get("error")
        if (isinstance(error, str) and error.strip()) or value.get("error_code") == "429050":
            raise TransientApiError(f"{component_type} fetch failed for {rsid}: transient SDK error stub")
    if isinstance(value, pd.DataFrame):
        value = value.to_dict(orient="records")
    if not isinstance(value, list):
        raise ApiError(f"{component_type} fetch failed for {rsid}: expected a list of component records")
    return value


def _component_records(value: Any, *, rsid: str, component_type: str) -> list[dict[str, Any]]:
    """`_response_rows` plus the per-row id every inventory family needs.

    The id is the key every writer, snapshot, and diff uses, so a row
    without one cannot be normalized. Used by the fetchers whose rows become
    SDR inventory: dimensions, metrics, segments, and calculated metrics.
    """
    rows = _response_rows(value, rsid=rsid, component_type=component_type)
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ApiError(f"{component_type} fetch failed for {rsid}: row {index} requires a nonempty string id")
    return rows


def _get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    """dict.get that treats pandas float-NaN like an absent key.

    The DataFrame-bound fetchers (VRS / report-suite listing) receive NaN for cells absent from
    ragged rows; str(NaN) is the literal "nan" and bool(NaN) is True, so NaN
    must resolve to `default` before any coercion. NaN is the only float that
    is != itself."""
    val = d.get(key, default)
    if isinstance(val, float) and val != val:
        return default
    return val


def _str_or_none(d: dict[str, Any], key: str) -> str | None:
    val = _get(d, key)
    if val is None:
        return None
    text = str(val)
    return text if text and text.strip() else None


def _bool(d: dict[str, Any], key: str, default: bool = False) -> bool:
    val = _get(d, key)
    return bool(val) if val is not None else default


def _int(d: dict[str, Any], key: str, default: int = 0) -> int:
    val = d.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _list(d: dict[str, Any], key: str) -> list[Any]:
    val = _get(d, key)
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
    """Passthrough of unknown keys, minus NaN cells from ragged DataFrame rows.

    A NaN that reaches a snapshot becomes a bare `NaN` token under json.dump
    (invalid strict JSON); dropping the key matches the raw path, where an
    absent cell is an absent key."""
    return {k: v for k, v in d.items() if k not in known and not (isinstance(v, float) and v != v)}


def fetch_report_suite(client: AaClient, rsid: str) -> models.ReportSuite:
    """Find the report suite with the given rsid. Uses extended_info to get
    currency / parentRsid / timezone fields."""
    started = time.monotonic()
    suites = _records(
        _retry_and_normalize(
            lambda: client.handle.getReportSuites(rsid_list=rsid, extended_info=True, limit=1000),
            policy=client.retry_policy,
            rsid=rsid,
        )
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.debug(
        "fetch_report_suite count=%s duration_ms=%s",
        len(suites),
        duration_ms,
        extra={"rsid": rsid, "count": len(suites), "duration_ms": duration_ms},
    )
    for raw in suites:
        if raw.get("rsid") == rsid:
            return models.ReportSuite(
                rsid=str(raw["rsid"]),
                name=str(_get(raw, "name", rsid)),
                timezone=_str_or_none(raw, "timezone") or _str_or_none(raw, "timezoneZoneinfo"),
                currency=_str_or_none(raw, "currency"),
                parent_rsid=_str_or_none(raw, "parentRsid"),
            )
    logger.error(
        "fetch_report_suite not_found rsid=%s",
        rsid,
        extra={"rsid": rsid, "error_class": "ReportSuiteNotFoundError"},
    )
    raise ReportSuiteNotFoundError(f"Report suite '{rsid}' not found")


def fetch_report_suite_summaries(client: AaClient) -> list[models.ReportSuiteSummary]:
    """Fetch every visible report suite as a list of ReportSuiteSummary.

    Replaces the v1.0–v1.2 pattern of `_records(client.handle.getReportSuites(...))`
    being called from CLI command code. Keeps the SDK boundary inside `api/`.

    Sort order: alphabetical by rsid."""
    started = time.monotonic()
    raw = _records(
        _retry_and_normalize(
            lambda: client.handle.getReportSuites(extended_info=True, limit=1000),
            policy=client.retry_policy,
        )
    )
    summaries = [
        models.ReportSuiteSummary(
            rsid=rsid,
            name=_str_or_none(r, "name"),
        )
        for r in raw
        if (rsid := _str_or_none(r, "rsid")) is not None
    ]
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.debug(
        "fetch_report_suite_summaries count=%s duration_ms=%s",
        len(summaries),
        duration_ms,
        extra={"count": len(summaries), "duration_ms": duration_ms},
    )
    return sorted(summaries, key=lambda s: s.rsid)


def fetch_report_suites_raw(client: AaClient) -> list[dict[str, Any]]:
    """One full report-suite listing as raw records, for callers that resolve
    many identifiers against a single fetch (batch/stats/inventory)."""
    return _records(
        _retry_and_normalize(
            lambda: client.handle.getReportSuites(extended_info=True, limit=1000),
            policy=client.retry_policy,
        )
    )


def resolve_rsid(
    client: AaClient,
    identifier: str,
    *,
    name_match: NameMatchStrategy = "insensitive",
    preloaded_suites: list[dict[str, Any]] | ReportSuiteIndex | None = None,
) -> tuple[list[str], bool]:
    """Resolve a user-supplied identifier to one or more canonical RSIDs.

    Resolution order:
      1. Exact RSID match (case-sensitive). Returns ([rsid], False).
      2. Name match per `name_match`:
           "exact":        case-sensitive name compare
           "insensitive":  case-insensitive name compare (DEFAULT —
                           preserves pre-v1.9.0 behavior)
           "fuzzy":        case-insensitive first; if no hit, SequenceMatcher
                           with threshold 0.85
      3. ReportSuiteNotFoundError otherwise.

    Multi-match in name_match!=insensitive mode raises AmbiguousMatchError
    with candidates exposed. insensitive mode preserves pre-v1.9.0 behavior
    (returns all matched RSIDs; CLI generates per-RSID).

    `preloaded_suites`, when given, is used instead of calling the SDK —
    callers resolving many identifiers (batch/stats/inventory) fetch the
    listing once via `fetch_report_suites_raw` and pass it in here.

    Returns (rsids, was_name_lookup). `rsids` is always a non-empty list
    on successful return.
    """
    if name_match not in _NAME_MATCH_VALUES:
        raise ValueError(f"name_match must be one of {list(_NAME_MATCH_VALUES)}, got {name_match!r}")

    logger.debug("resolve_rsid identifier-input strategy=%s", name_match)
    if preloaded_suites is not None:
        suites = preloaded_suites
    else:
        suites = _records(
            _retry_and_normalize(
                lambda: client.handle.getReportSuites(extended_info=True, limit=1000),
                policy=client.retry_policy,
            )
        )

    index = suites if isinstance(suites, ReportSuiteIndex) else None
    if index is not None:
        suites = index.rows

    # 1) Exact RSID match — RSIDs are distinct and case-sensitive
    id_matches = (
        identifier in index.rsids
        if index is not None and not index.scan_rsids
        else any(raw.get("rsid") == identifier for raw in suites)
    )
    if id_matches:
        logger.debug(
            "resolve_rsid resolved count=%s was_name_lookup=false strategy=%s",
            1,
            name_match,
            extra={"count": 1, "name_match_strategy": name_match},
        )
        return [identifier], False

    # 2) Name match — strategy-dependent
    name_matches: list[tuple[str, str]] = []  # (rsid, name)
    if index is not None and not index.scan_names:
        matches = (
            index.exact_names.get(identifier, [])
            if name_match == "exact"
            else index.folded_names.get(identifier.casefold(), [])
        )
        name_matches = [(str(raw["rsid"]), str(raw["name"])) for raw in matches]
    elif name_match == "exact":
        name_matches.extend((str(raw["rsid"]), str(raw["name"])) for raw in suites if raw.get("name") == identifier)
    else:  # insensitive or fuzzy
        target = identifier.casefold()
        for raw in suites:
            n = raw.get("name")
            if n is not None and str(n).casefold() == target:
                name_matches.append((str(raw["rsid"]), str(n)))

    # 2b) Fuzzy fallback when nothing matched insensitively
    if name_match == "fuzzy" and not name_matches:
        target = identifier.casefold()
        for raw in suites:
            n = raw.get("name")
            if n is None:
                continue
            ratio = SequenceMatcher(None, target, str(n).casefold()).ratio()
            if ratio >= _FUZZY_THRESHOLD:
                name_matches.append((str(raw["rsid"]), str(n)))

    if not name_matches:
        raise ReportSuiteNotFoundError(
            f"report suite '{identifier}' not found (matched neither rsid nor name)",
        )

    if len(name_matches) > 1 and name_match != "insensitive":
        # exact and fuzzy treat multi-match as ambiguous; insensitive returns
        # all (preserves pre-v1.9.0 behavior where the CLI generates per-RSID).
        raise AmbiguousMatchError(
            f"identifier '{identifier}' resolved to {len(name_matches)} candidates",
            candidates=name_matches,
        )

    rsids = [rsid for rsid, _ in name_matches]
    logger.debug(
        "resolve_rsid resolved count=%s was_name_lookup=true strategy=%s",
        len(rsids),
        name_match,
        extra={"count": len(rsids), "name_match_strategy": name_match},
    )
    return rsids, True


def fetch_dimensions(client: AaClient, rsid: str) -> list[models.Dimension]:
    started = time.monotonic()
    raws = _retry_and_normalize(
        lambda: _component_records(
            client.handle.getDimensions(rsid=rsid, description=True, tags=True, format="raw"),
            rsid=rsid,
            component_type="dimension",
        ),
        policy=client.retry_policy,
        rsid=rsid,
        component_type="dimension",
    )
    known = {"id", "name", "type", "category", "parent", "pathable", "description", "tags"}
    out = [
        models.Dimension(
            id=str(r["id"]),
            name=str(_get(r, "name", r["id"])),
            type=str(_get(r, "type", "unknown")),
            category=_str_or_none(r, "category"),
            parent=str(_get(r, "parent") or ""),
            pathable=_bool(r, "pathable"),
            description=_str_or_none(r, "description"),
            tags=_list(r, "tags"),
            extra=_extra(r, known),
        )
        for r in raws
    ]
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=dimension count=%s duration_ms=%s",
        rsid,
        len(out),
        duration_ms,
        extra={
            "rsid": rsid,
            "component_type": "dimension",
            "count": len(out),
            "duration_ms": duration_ms,
        },
    )
    return out


def fetch_metrics(client: AaClient, rsid: str) -> list[models.Metric]:
    started = time.monotonic()
    raws = _retry_and_normalize(
        lambda: _component_records(
            client.handle.getMetrics(rsid=rsid, description=True, tags=True, format="raw"),
            rsid=rsid,
            component_type="metric",
        ),
        policy=client.retry_policy,
        rsid=rsid,
        component_type="metric",
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
    out = [
        models.Metric(
            id=str(r["id"]),
            name=str(_get(r, "name", r["id"])),
            type=str(_get(r, "type", "unknown")),
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
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=metric count=%s duration_ms=%s",
        rsid,
        len(out),
        duration_ms,
        extra={
            "rsid": rsid,
            "component_type": "metric",
            "count": len(out),
            "duration_ms": duration_ms,
        },
    )
    return out


def fetch_segments(client: AaClient, rsid: str) -> list[models.Segment]:
    """Pulls segments for the rsid, with extended_info for the `definition` body."""
    started = time.monotonic()
    raws = _retry_and_normalize(
        lambda: _component_records(
            client.handle.getSegments(rsids_list=[rsid], extended_info=True, format="raw", limit=1000),
            rsid=rsid,
            component_type="segment",
        ),
        policy=client.retry_policy,
        rsid=rsid,
        component_type="segment",
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
    out = [
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
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=segment count=%s duration_ms=%s",
        rsid,
        len(out),
        duration_ms,
        extra={
            "rsid": rsid,
            "component_type": "segment",
            "count": len(out),
            "duration_ms": duration_ms,
        },
    )
    return out


def fetch_calculated_metrics(
    client: AaClient,
    rsid: str,
) -> list[models.CalculatedMetric]:
    """Pulls calculated metrics for the rsid, with extended_info for `definition`."""
    started = time.monotonic()
    raws = _retry_and_normalize(
        lambda: _component_records(
            client.handle.getCalculatedMetrics(rsids_list=[rsid], extended_info=True, format="raw", limit=1000),
            rsid=rsid,
            component_type="calculated_metric",
        ),
        policy=client.retry_policy,
        rsid=rsid,
        component_type="calculated_metric",
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
    out = [
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
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=calculated_metric count=%s duration_ms=%s",
        rsid,
        len(out),
        duration_ms,
        extra={
            "rsid": rsid,
            "component_type": "calculated_metric",
            "count": len(out),
            "duration_ms": duration_ms,
        },
    )
    return out


def _is_usable_vrs_row(row: Any) -> bool:
    """True when `row` is a mapping carrying an id that can name a component.

    `_str_or_none` accepts a non-string id and rejects the empty string and
    the float NaN a DataFrame conversion leaves for an absent cell. A numeric
    id is kept and coerced, matching
    `fetch_virtual_report_suite_summaries`, so the generated SDR never holds
    fewer virtual report suites than `--list-virtual-reportsuites` shows.
    """
    return isinstance(row, dict) and _str_or_none(row, "id") is not None


def _finalize_vrs_fetch(
    raws: list[dict[str, Any]],
    parent_rsid: str,
    started_monotonic: float,
    *,
    expansion_level: str,
    copy_rows: bool = False,
    parent_counts: tuple[int, int] | None = None,
) -> list[models.VirtualReportSuite]:
    """Apply parentRsid filter, build VRS rows, emit DEBUG + INFO logs.

    Shared by the default and count_only=True paths (both request full
    expansion). The expansion_level string is descriptive of the payload
    shape (always "full" today) and goes into the component_fetch INFO
    record; it does NOT control the FetchOutcome.expansion_level field
    (that's the caller's responsibility).

    Unusable rows are already gone: `enumerate_vrs` drops them as it reads
    the listing, so `parent_counts` and the `vrs_parent_filter` arithmetic
    below describe the same set of rows whether or not a shared VrsSource is
    in play.
    """
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
    out = [
        models.VirtualReportSuite(
            id=str(r["id"]),
            name=str(_get(r, "name", r["id"])),
            parent_rsid=str(r.get("parentRsid", "")),
            timezone=_str_or_none(r, "timezone") or _str_or_none(r, "timezoneZoneinfo"),
            description=_str_or_none(r, "description"),
            segment_list=_list(r, "segmentList"),
            curated_components=_list(r, "curatedComponents"),
            modified=_str_or_none(r, "modified"),
            extra=_extra(r, known),
        )
        for source_row in raws
        if source_row.get("parentRsid") == parent_rsid
        for r in [deepcopy(source_row) if copy_rows else source_row]
    ]
    # v1.7.0 Item D — structured DEBUG when client-side parentRsid filter drops rows.
    pulled, dropped_no_parent = parent_counts if parent_counts is not None else (len(raws), 0)
    if len(out) != pulled:
        if parent_counts is None:
            dropped_no_parent = sum(1 for r in raws if not _get(r, "parentRsid"))
        dropped_other_parent = pulled - len(out) - dropped_no_parent
        logger.debug(
            "vrs_parent_filter rsid=%s pulled=%s filtered=%s dropped_no_parent=%s dropped_other_parent=%s",
            parent_rsid,
            pulled,
            len(out),
            dropped_no_parent,
            dropped_other_parent,
            extra={
                "rsid": parent_rsid,
                "pulled": pulled,
                "filtered": len(out),
                "dropped_no_parent": dropped_no_parent,
                "dropped_other_parent": dropped_other_parent,
            },
        )
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=virtual_report_suite count=%s duration_ms=%s expansion_level=%s",
        parent_rsid,
        len(out),
        duration_ms,
        expansion_level,
        extra={
            "rsid": parent_rsid,
            "component_type": "virtual_report_suite",
            "count": len(out),
            "duration_ms": duration_ms,
            "expansion_level": expansion_level,
        },
    )
    return out


def fetch_virtual_report_suites(
    client: AaClient,
    parent_rsid: str,
    *,
    count_only: bool = False,
    source: VrsSource | None = None,
) -> models.FetchOutcome[models.VirtualReportSuite]:
    """Lists VRS visible to the org, filtered to those whose parent matches.

    The SDK call has no rsid filter — we filter client-side after pulling all
    VRS via extended_info=True (which gives us `parentRsid`).

    Always full expansion. The SDK's extended_info=False path strips every
    row to {name, vrsid} — no id, no parentRsid — so a reduced-expansion
    response cannot support the client-side parent filter and can only ever
    yield zero rows. That constraint retired two earlier paths:

      * the v1.7.0 two-rung ladder's minimal fallback, which spent a second
        full retry budget to return an empty "partial" result;
      * the v1.7.2 count_only=True minimal call, which made every count-only
        consumer (describe / stats / inventory) report 0 VRS.

    Single rung, full retry budget for transient errors; ``KeyError('content')``
    is classified permanent (v1.16.1) and fast-fails without retries. On
    exhaustion, returns FetchOutcome.degraded() (data=[]) (preserves v1.6.1
    graceful-degrade after a customer hit `KeyError: 'content'` from
    `aanalytics2` 0.5.1 when Adobe's VRS endpoint returned HTTP 500 — the SDK
    unconditionally indexes `vrsid['content']` on the response envelope,
    which is absent on error).

    count_only=True keeps its contract — single call, healthy/degraded,
    expansion_level=None on the outcome — and differs only in the
    `expansion_level=count_only` label on the failure WARNING, so log
    analytics can still distinguish the two failure paths.
    """
    started = time.monotonic()

    def _on_attempt(a: int, m: int, d: float, e: BaseException) -> None:
        log_retry_attempt(
            a,
            m,
            d,
            e,
            rsid=parent_rsid,
            component_type="virtual_report_suite",
        )

    def enumerate_vrs() -> list[dict[str, Any]]:
        # `_response_rows`, not `_records`: a mapping-shaped error stub used to
        # be wrapped into a single row that the parent filter then dropped,
        # reporting a failed endpoint as a healthy org with zero VRS.
        return _response_rows(
            with_retries(
                lambda: classify_transient_sdk_call(
                    lambda: classify_permanent_vrs_shape_error(
                        lambda: client.handle.getVirtualReportSuites(extended_info=True, limit=1000),
                    ),
                    component_type="virtual_report_suite",
                ),
                policy=client.retry_policy,
                on_attempt=_on_attempt,
            ),
            rsid=parent_rsid,
            component_type="virtual_report_suite",
        )

    if source is not None:
        source.validate(client)
    try:
        # One shape for both paths: `VrsRows.build` applies the usable-row
        # predicate, indexes by parent, and reports how many rows it dropped.
        # A shared source carries that count to every suite in the batch, so
        # all of them see the listing was read incompletely.
        shared = (
            source.get(client, enumerate_vrs, usable=_is_usable_vrs_row)
            if source is not None
            else VrsRows.build(enumerate_vrs(), usable=_is_usable_vrs_row)
        )
        raws = shared.rows
    except Exception as e:
        failure_label = "count_only" if count_only else "exhausted"
        logger.warning(
            "virtual report suites fetch failed rsid=%s expansion_level=%s error_class=%s",
            parent_rsid,
            failure_label,
            type(e).__name__,
            extra={
                "rsid": parent_rsid,
                "component_type": "virtual_report_suite",
                "expansion_level": failure_label,
                "error_class": type(e).__name__,
            },
        )
        if isinstance(e, VrsEndpointShapeError):
            logger.warning(
                "vrs_unavailable rsid=%s likely_cause=empty_tenant_or_permanent_endpoint_shape_error",
                parent_rsid,
                extra={
                    "rsid": parent_rsid,
                    "component_type": "virtual_report_suite",
                    "likely_cause": "empty_tenant_or_permanent_endpoint_shape_error",
                },
            )
        return models.FetchOutcome.degraded()
    parent_counts = None
    if shared.by_parent is not None and type(parent_rsid) is str:
        raws = shared.by_parent.get(parent_rsid, [])
        parent_counts = (len(shared.rows), shared.no_parent)
    out = _finalize_vrs_fetch(
        raws, parent_rsid, started, expansion_level="full", copy_rows=source is not None, parent_counts=parent_counts
    )
    if shared.dropped:
        # Rows we could not read are missing from the capture, and a healthy
        # capture writes no `degraded_components` entry, so the next --diff
        # would report them as deleted suites and --watch would fire a false
        # change event. Report the rows we did read, and mark the family
        # degraded so a comparison suppresses the section instead.
        logger.warning(
            "vrs_rows_skipped rsid=%s component_type=virtual_report_suite count=%s; "
            "marking the family degraded so a diff does not read them as removed",
            parent_rsid,
            shared.dropped,
            extra={
                "rsid": parent_rsid,
                "component_type": "virtual_report_suite",
                "count": shared.dropped,
            },
        )
        return models.FetchOutcome(data=out, status="degraded", expansion_level=None)
    return models.FetchOutcome.healthy(out)


def fetch_virtual_report_suite_summaries(
    client: AaClient,
) -> list[models.VirtualReportSuiteSummary]:
    """Fetch every visible virtual report suite as a list of VirtualReportSuiteSummary.

    Replaces the v1.0–v1.2 pattern of `_records(client.handle.getVirtualReportSuites(...))`
    being called from CLI command code. Keeps the SDK boundary inside `api/`.

    Sort order: alphabetical by id.

    SDK exceptions are normalized to `ApiError` so the CLI's existing typed
    catch (`except ApiError → exit 12`) works regardless of the underlying
    shape. Discovery is NOT graceful-degrade like the generate path: the
    user explicitly asked for the list, and silently returning `[]` on a
    broken endpoint would misleadingly suggest the org has no VRS. Added
    in v1.6.1 to cover the same `KeyError: 'content'` failure mode that
    crashed the generate path."""
    started = time.monotonic()
    try:
        raw = _records(
            with_retries(
                lambda: classify_transient_sdk_call(
                    lambda: client.handle.getVirtualReportSuites(extended_info=True, limit=1000),
                    component_type="virtual_report_suite",
                ),
                policy=client.retry_policy,
                on_attempt=lambda a, m, d, e: log_retry_attempt(
                    a,
                    m,
                    d,
                    e,
                    component_type="virtual_report_suite",
                ),
            )
        )
    except ApiError:
        raise  # already typed; let it bubble
    except Exception as e:
        # DEBUG (not WARNING) — the CLI prints the ApiError message itself, so a
        # WARNING here would double-noise interactive output. Structured field
        # gives log aggregation a searchable hook without user-visible churn.
        logger.debug(
            "virtual report suites fetch failed error_class=%s",
            type(e).__name__,
            extra={
                "component_type": "virtual_report_suite",
                "error_class": type(e).__name__,
            },
        )
        raise ApiError(
            f"virtual report suites fetch failed: {type(e).__name__}: {e}",
        ) from e
    summaries = [
        models.VirtualReportSuiteSummary(
            id=str(r.get("id", "")),
            name=_str_or_none(r, "name"),
            parent_rsid=str(r.get("parentRsid", "")),
        )
        for r in raw
        if r.get("id")
    ]
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.debug(
        "fetch_virtual_report_suite_summaries count=%s duration_ms=%s",
        len(summaries),
        duration_ms,
        extra={"count": len(summaries), "duration_ms": duration_ms},
    )
    return sorted(summaries, key=lambda s: s.id)


_CLASSIFICATION_ID_KEYS = ("id", "dataSetId", "datasetId", "data_set_id")
_CLASSIFICATION_NAME_KEYS = ("name", "displayName", "display_name")


def _first_present(d: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty stringable value among `keys` in `d`.

    Filters None, empty string, AND pandas NaN (float-NaN appears after a
    DataFrame.to_dict() when a row is missing a column other rows have)."""
    for k in keys:
        v = d.get(k)
        if v is None or v == "":
            continue
        # pandas yields float-NaN for missing cells; NaN is the only float != itself
        if isinstance(v, float) and v != v:
            continue
        return str(v)
    return None


def _merge_classification(
    first: models.ClassificationDataset,
    later: models.ClassificationDataset,
) -> models.ClassificationDataset:
    """Combine two rows that name the same dataset.

    A passthrough key whose value differs between the rows describes the
    pair, not the dataset (the metric id, for one), so keeping either row's
    value would make a capture depend on the order Adobe listed the pairs,
    and an unchanged report suite could then diff as modified under
    `--extended-fields`. Only the keys the rows agree on survive, which is
    the same answer whatever the order.

    The name needs the same treatment: a pair row carrying none of the name
    keys falls back to the dataset id, so keeping the first row's name would
    read as `ds1` in one order and `Campaign` in the other. The row that
    carries a real name wins, and when both do the earlier one is kept.
    """
    shared = {k: v for k, v in first.extra.items() if k in later.extra and later.extra[k] == v}
    name = later.name if first.name == first.id and later.name != later.id else first.name
    return dataclasses.replace(first, name=name, extra=shared)


def fetch_classification_datasets(
    client: AaClient,
    rsid: str,
    *,
    count_only: bool = False,
) -> models.FetchOutcome[models.ClassificationDataset]:
    """Lists classification datasets compatible with metrics in the report suite.

    This is the only enumeration path Adobe Analytics API 2.0 exposes for
    classifications — there is no per-dimension list endpoint.

    The endpoint's response shape varies by org/RS. We tolerate `id` /
    `dataSetId` / `datasetId` for the identifier, and `name` / `displayName`
    for the human-readable name. Records missing both id-like keys are skipped.
    Any failure of the underlying call returns an empty list rather than
    breaking the whole SDR — classifications are best-effort in v0.1.x.

    `count_only` (v1.7.2+) is accepted for API symmetry with
    fetch_virtual_report_suites but is currently a no-op for classifications:
    the underlying getClassificationDatasets SDK call has no extended_info knob
    — the response is always minimal (id/name/rsid). Reserved for forward-compat
    if the endpoint ever gains an expansion knob.
    """
    # count_only is accepted for API symmetry with fetch_virtual_report_suites
    # but is currently a no-op for classifications: getClassificationDatasets
    # has no extended_info knob in aanalytics2 0.5.1. If a future SDK release
    # adds one, wire count_only=True → extended_info=False here and update
    # docs/superpowers/specs/2026-05-08-aa-auto-sdr-vrs-hardening-design.md
    # §3.1 "Classifications parity" with the implementation status.
    _ = count_only
    started = time.monotonic()
    try:
        raws = _records(
            with_retries(
                lambda: classify_transient_sdk_call(
                    lambda: client.handle.getClassificationDatasets(rsid=rsid),
                    component_type="classification",
                ),
                policy=client.retry_policy,
                on_attempt=lambda a, m, d, e: log_retry_attempt(
                    a,
                    m,
                    d,
                    e,
                    rsid=rsid,
                    component_type="classification",
                ),
            )
        )
    except Exception as e:  # wrapper raises various exception types
        logger.warning(
            "classifications fetch failed rsid=%s error_class=%s",
            rsid,
            type(e).__name__,
            extra={
                "rsid": rsid,
                "component_type": "classification",
                "error_class": type(e).__name__,
            },
        )
        return models.FetchOutcome.degraded()

    known = {*_CLASSIFICATION_ID_KEYS, *_CLASSIFICATION_NAME_KEYS, "rsid"}
    # One row per dataset-and-metric pair, so a dataset compatible with
    # several metrics arrives several times. Collapse to one row per dataset
    # here, at the boundary every consumer reads: `--describe-reportsuite`,
    # `--stats`, `--inventory-summary`, and
    # `--list-classification-datasets` all call this fetcher, so deduping
    # further downstream would make them report a different count than the
    # SDR built in the same run.
    by_id: dict[str, models.ClassificationDataset] = {}
    pairs = 0
    for r in raws:
        ds_id = _first_present(r, _CLASSIFICATION_ID_KEYS)
        if ds_id is None:
            continue
        pairs += 1
        ds_name = _first_present(r, _CLASSIFICATION_NAME_KEYS) or ds_id
        dataset = models.ClassificationDataset(
            id=ds_id,
            name=ds_name,
            rsid=str(r.get("rsid", rsid)),
            extra=_extra(r, known),
        )
        seen = by_id.get(ds_id)
        by_id[ds_id] = dataset if seen is None else _merge_classification(seen, dataset)
    out = list(by_id.values())
    if pairs != len(out):
        logger.debug(
            "classification_pairs_collapsed rsid=%s component_type=classification count=%s",
            rsid,
            pairs - len(out),
            extra={"rsid": rsid, "component_type": "classification", "count": pairs - len(out)},
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=classification count=%s duration_ms=%s",
        rsid,
        len(out),
        duration_ms,
        extra={
            "rsid": rsid,
            "component_type": "classification",
            "count": len(out),
            "duration_ms": duration_ms,
        },
    )
    return models.FetchOutcome.healthy(out)
