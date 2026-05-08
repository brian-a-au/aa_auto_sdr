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

import logging
import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from aa_auto_sdr.api import models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import RetryPolicy, with_retries
from aa_auto_sdr.core.exceptions import ApiError, ReportSuiteNotFoundError, TransientApiError

logger = logging.getLogger(__name__)


def _classify_transient_sdk_call[T](fn: Callable[[], T], *, component_type: str | None = None) -> T:
    """Run `fn`, classifying SDK-shape failures as `TransientApiError`.

    Per spike (docs/superpowers/spikes/2026-05-08-aanalytics2-resilience-spike.md):
    aanalytics2 0.5.1 surfaces transient HTTP failures (5xx after urllib3
    retries, malformed bodies) as bare KeyError (from indexing into stub
    error dicts like vrsid['content']) or ValueError (from pandas DataFrame
    construction over malformed payloads). This helper translates those to
    TransientApiError so is_retryable can dispatch on a typed signal — used
    by both _retry_and_normalize (bubbling fetchers) and the VRS ladder
    rungs (where each rung needs the classifier independently so the outer
    try/except can fall to the next rung).
    """
    try:
        return fn()
    except (KeyError, ValueError) as e:
        ctx = f"{component_type} " if component_type else ""
        raise TransientApiError(f"{ctx}transient SDK failure: {type(e).__name__}: {e}") from e


def _log_retry_attempt(
    attempt: int,
    max_attempts: int,
    delay_s: float,
    exc: BaseException,
    *,
    rsid: str | None = None,
    component_type: str | None = None,
) -> None:
    """on_attempt callback for with_retries. Emits a DEBUG record per retry.

    Vocabulary-compliant fields (per docs/LOGGING_STYLE.md §6.1): only
    ``retry_attempt``, ``error_class``, ``rsid``, ``component_type`` go into
    ``extra={}``. ``max_attempts`` / ``delay_s`` ride along the message string
    for human readability without being formally indexed (the structured
    sink can still parse the message if it cares)."""
    logger.debug(
        "retry_attempt attempt=%s/%s delay_s=%.3f error_class=%s",
        attempt,
        max_attempts,
        delay_s,
        type(exc).__name__,
        extra={
            "retry_attempt": attempt,
            "error_class": type(exc).__name__,
            "rsid": rsid,
            "component_type": component_type,
        },
    )


def _retry_and_normalize[T](
    fn: Callable[[], T],
    *,
    policy: RetryPolicy,
    rsid: str | None = None,
    component_type: str | None = None,
) -> T:
    """Run `fn` under `policy`, classifying SDK-shape failures as transient.

    Two responsibilities:

    1. Inner classifier (via _classify_transient_sdk_call) — translates the SDK's
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
            lambda: _classify_transient_sdk_call(fn, component_type=component_type),
            policy=policy,
            on_attempt=lambda a, m, d, e: _log_retry_attempt(
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
    started = time.monotonic()
    suites = _records(
        _retry_and_normalize(
            lambda: client.handle.getReportSuites(extended_info=True),
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
                name=str(raw.get("name", rsid)),
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
            lambda: client.handle.getReportSuites(extended_info=True),
            policy=client.retry_policy,
        )
    )
    summaries = [
        models.ReportSuiteSummary(
            rsid=str(r.get("rsid", "")),
            name=_str_or_none(r, "name"),
        )
        for r in raw
        if r.get("rsid")
    ]
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.debug(
        "fetch_report_suite_summaries count=%s duration_ms=%s",
        len(summaries),
        duration_ms,
        extra={"count": len(summaries), "duration_ms": duration_ms},
    )
    return sorted(summaries, key=lambda s: s.rsid)


def resolve_rsid(client: AaClient, identifier: str) -> tuple[list[str], bool]:
    """Resolve a user-supplied identifier to one or more canonical RSIDs.

    Resolution order (matches cja_auto_sdr convention):
      1. RSID exact match against the rsid field. RSIDs are distinct, so this
         returns exactly one result. Returns ([rsid], False).
      2. Name exact match (case-insensitive) against the name field. Names are
         NOT guaranteed unique, so multiple suites may match. Returns the
         RSIDs of all matches as ([rsid_1, rsid_2, ...], True). The caller
         (CLI generate command) generates an SDR per RSID.
      3. ReportSuiteNotFoundError otherwise.

    Returns (rsids, was_name_lookup). `rsids` is always a non-empty list.
    """
    logger.debug("resolve_rsid identifier-input")
    suites = _records(
        _retry_and_normalize(
            lambda: client.handle.getReportSuites(extended_info=True),
            policy=client.retry_policy,
        )
    )

    # 1) Exact RSID match — RSIDs are distinct
    for raw in suites:
        if raw.get("rsid") == identifier:
            logger.debug(
                "resolve_rsid resolved count=%s was_name_lookup=false",
                1,
                extra={"count": 1},
            )
            return [identifier], False

    # 2) Case-insensitive exact name match — may match multiple suites
    target = identifier.casefold()
    name_matches = [
        str(raw["rsid"]) for raw in suites if raw.get("name") is not None and str(raw["name"]).casefold() == target
    ]
    if name_matches:
        logger.debug(
            "resolve_rsid resolved count=%s was_name_lookup=true",
            len(name_matches),
            extra={"count": len(name_matches)},
        )
        return name_matches, True

    raise ReportSuiteNotFoundError(
        f"report suite '{identifier}' not found (matched neither rsid nor name)",
    )


def fetch_dimensions(client: AaClient, rsid: str) -> list[models.Dimension]:
    started = time.monotonic()
    raws = _records(
        _retry_and_normalize(
            lambda: client.handle.getDimensions(rsid=rsid, description=True, tags=True),
            policy=client.retry_policy,
            rsid=rsid,
            component_type="dimension",
        )
    )
    known = {"id", "name", "type", "category", "parent", "pathable", "description", "tags"}
    out = [
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
    # NOTE: `dataGroup=True` removed in v0.1.1. The aanalytics2 wrapper internally
    # slices the response DataFrame to a hardcoded column list that includes
    # `dataGroup` — but the API doesn't always return that column for every RS,
    # which raises `KeyError: "['dataGroup'] not in index"`. Until upstream fixes
    # the slice or we figure out which RS shapes are safe, we skip the flag and
    # leave `data_group` as None on the Metric model.
    started = time.monotonic()
    raws = _records(
        _retry_and_normalize(
            lambda: client.handle.getMetrics(rsid=rsid, description=True, tags=True),
            policy=client.retry_policy,
            rsid=rsid,
            component_type="metric",
        )
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
    raws = _records(
        _retry_and_normalize(
            lambda: client.handle.getSegments(rsids_list=[rsid], extended_info=True),
            policy=client.retry_policy,
            rsid=rsid,
            component_type="segment",
        )
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
    raws = _records(
        _retry_and_normalize(
            lambda: client.handle.getCalculatedMetrics(rsids_list=[rsid], extended_info=True),
            policy=client.retry_policy,
            rsid=rsid,
            component_type="calculated_metric",
        )
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


def fetch_virtual_report_suites(
    client: AaClient,
    parent_rsid: str,
) -> list[models.VirtualReportSuite]:
    """Lists VRS visible to the org, filtered to those whose parent matches.

    The SDK call has no rsid filter — we filter client-side after pulling all
    VRS via extended_info=True (which gives us `parentRsid`).

    Any failure of the underlying call returns an empty list rather than
    breaking the whole SDR — VRS are best-effort. v1.6.1 added this guard
    after a customer hit `KeyError: 'content'` from `aanalytics2` 0.5.1 when
    the Adobe VRS endpoint returned HTTP 500 for their org; the SDK
    unconditionally indexes `vrsid['content']` on the response envelope,
    which is absent on error. Mirrors the classifications pattern below."""
    started = time.monotonic()
    try:
        raws = _records(
            with_retries(
                lambda: _classify_transient_sdk_call(
                    lambda: client.handle.getVirtualReportSuites(extended_info=True),
                    component_type="virtual_report_suite",
                ),
                policy=client.retry_policy,
                on_attempt=lambda a, m, d, e: _log_retry_attempt(
                    a,
                    m,
                    d,
                    e,
                    rsid=parent_rsid,
                    component_type="virtual_report_suite",
                ),
            )
        )
    except Exception as e:  # SDK raises KeyError on HTTP 500, plus other shapes
        logger.warning(
            "virtual report suites fetch failed rsid=%s error_class=%s",
            parent_rsid,
            type(e).__name__,
            extra={
                "rsid": parent_rsid,
                "component_type": "virtual_report_suite",
                "error_class": type(e).__name__,
            },
        )
        return []
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
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "component_fetch rsid=%s component_type=virtual_report_suite count=%s duration_ms=%s",
        parent_rsid,
        len(out),
        duration_ms,
        extra={
            "rsid": parent_rsid,
            "component_type": "virtual_report_suite",
            "count": len(out),
            "duration_ms": duration_ms,
        },
    )
    return out


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
                lambda: _classify_transient_sdk_call(
                    lambda: client.handle.getVirtualReportSuites(extended_info=True),
                    component_type="virtual_report_suite",
                ),
                policy=client.retry_policy,
                on_attempt=lambda a, m, d, e: _log_retry_attempt(
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
    started = time.monotonic()
    try:
        raws = _records(
            with_retries(
                lambda: _classify_transient_sdk_call(
                    lambda: client.handle.getClassificationDatasets(rsid=rsid),
                    component_type="classification",
                ),
                policy=client.retry_policy,
                on_attempt=lambda a, m, d, e: _log_retry_attempt(
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
    return out
