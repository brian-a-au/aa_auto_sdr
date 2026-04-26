"""Inspect command handlers: per-component listing + per-RS describe.

Each list-X command resolves the identifier (RSID or name), runs the relevant
fetcher across resolved RSIDs (multi-match-by-name produces one record-set per
RSID with a disambiguating 'rsid' column), applies filter/sort/limit, renders.

run_describe_reportsuite returns metadata + counts (no full SDR generated)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.cli._filters import apply_filters
from aa_auto_sdr.cli.list_output import render_records
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    AaAutoSdrError,
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)

_EXIT_OK = 0
_EXIT_GENERIC = 1
_EXIT_USAGE = 2
_EXIT_CONFIG = 10
_EXIT_AUTH = 11
_EXIT_API = 12
_EXIT_NOT_FOUND = 13

_METRIC_COLS = [
    "id",
    "name",
    "type",
    "category",
    "precision",
    "segmentable",
    "description",
    "tags",
    "data_group",
    "extra",
]
_DIMENSION_COLS = ["id", "name", "type", "category", "parent", "pathable", "description", "tags", "extra"]
_SEGMENT_COLS = [
    "id",
    "name",
    "description",
    "rsid",
    "owner_id",
    "definition",
    "compatibility",
    "tags",
    "created",
    "modified",
    "extra",
]
_CALCULATED_COLS = [
    "id",
    "name",
    "description",
    "rsid",
    "owner_id",
    "polarity",
    "precision",
    "type",
    "definition",
    "tags",
    "categories",
    "extra",
]
_CLASSIFICATION_COLS = ["id", "name", "rsid", "extra"]
_DESCRIBE_COLS = [
    "rsid",
    "name",
    "timezone",
    "currency",
    "parent_rsid",
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
]

_METRIC_SORT = ("id", "name", "type", "category")
_DIMENSION_SORT = ("id", "name", "type", "category")
_SEGMENT_SORT = ("id", "name", "rsid")
_CALCULATED_SORT = ("id", "name", "rsid", "polarity")
_CLASSIFICATION_SORT = ("id", "name", "rsid")


def _resolve_output(output: str | None) -> Path | None:
    if output is None:
        return None
    if output == "-":
        return Path("-")
    return Path(output)


def _bootstrap(profile: str | None) -> tuple[AaClient | None, int]:
    """Resolve credentials and build a client. Returns (client, 0) on success
    or (None, exit_code) on failure."""
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return None, _EXIT_CONFIG

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return None, _EXIT_AUTH
    return client, _EXIT_OK


def _list_per_component(
    *,
    identifier: str,
    profile: str | None,
    format_name: str | None,
    output: str | None,
    name_filter: str | None,
    name_exclude: str | None,
    sort_field: str | None,
    limit: int | None,
    fetcher: Callable[[AaClient, str], list[Any]],
    columns: list[str],
    sort_allowlist: tuple[str, ...],
) -> int:
    """Generic list-X handler: resolve identifier → fetch per RSID → flatten →
    filter → render."""
    client, rc = _bootstrap(profile)
    if client is None:
        return rc

    try:
        canonical_rsids, _was_name = fetch.resolve_rsid(client, identifier)
    except ReportSuiteNotFoundError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_NOT_FOUND
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API

    multi = len(canonical_rsids) > 1
    if multi:
        import sys

        print(
            f"{identifier!r} matches {len(canonical_rsids)} report suites: {', '.join(canonical_rsids)}",
            file=sys.stderr,
            flush=True,
        )

    records: list[dict[str, Any]] = []
    cols = (["rsid", *columns]) if multi else columns
    for canonical_rsid in canonical_rsids:
        try:
            items = fetcher(client, canonical_rsid)
        except ApiError as e:
            print(f"api error: {e}", flush=True)
            return _EXIT_API
        except AaAutoSdrError as e:
            print(f"error: {e}", flush=True)
            return _EXIT_GENERIC
        for item in items:
            row = asdict(item)
            if multi:
                row = {"rsid": canonical_rsid, **row}
            records.append(row)

    chosen_sort = sort_field or sort_allowlist[0]
    try:
        filtered = apply_filters(
            records,
            name_filter=name_filter,
            name_exclude=name_exclude,
            sort_field=chosen_sort,
            limit=limit,
            sort_field_allowlist=sort_allowlist,
        )
    except ValueError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_USAGE

    return render_records(
        filtered,
        format_name=format_name,
        output=_resolve_output(output),
        columns=cols,
    )


def run_list_metrics(**kwargs: Any) -> int:
    return _list_per_component(
        fetcher=fetch.fetch_metrics,
        columns=_METRIC_COLS,
        sort_allowlist=_METRIC_SORT,
        **kwargs,
    )


def run_list_dimensions(**kwargs: Any) -> int:
    return _list_per_component(
        fetcher=fetch.fetch_dimensions,
        columns=_DIMENSION_COLS,
        sort_allowlist=_DIMENSION_SORT,
        **kwargs,
    )


def run_list_segments(**kwargs: Any) -> int:
    return _list_per_component(
        fetcher=fetch.fetch_segments,
        columns=_SEGMENT_COLS,
        sort_allowlist=_SEGMENT_SORT,
        **kwargs,
    )


def run_list_calculated_metrics(**kwargs: Any) -> int:
    return _list_per_component(
        fetcher=fetch.fetch_calculated_metrics,
        columns=_CALCULATED_COLS,
        sort_allowlist=_CALCULATED_SORT,
        **kwargs,
    )


def run_list_classification_datasets(**kwargs: Any) -> int:
    return _list_per_component(
        fetcher=fetch.fetch_classification_datasets,
        columns=_CLASSIFICATION_COLS,
        sort_allowlist=_CLASSIFICATION_SORT,
        **kwargs,
    )


def run_describe_reportsuite(
    *,
    identifier: str,
    profile: str | None,
    format_name: str | None,
    output: str | None,
) -> int:
    """Print metadata + per-component counts for one RS (or several on multi-match)."""
    client, rc = _bootstrap(profile)
    if client is None:
        return rc

    try:
        canonical_rsids, _was_name = fetch.resolve_rsid(client, identifier)
    except ReportSuiteNotFoundError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_NOT_FOUND
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API

    records: list[dict[str, Any]] = []
    for canonical_rsid in canonical_rsids:
        try:
            rs = fetch.fetch_report_suite(client, canonical_rsid)
            dims = fetch.fetch_dimensions(client, canonical_rsid)
            mets = fetch.fetch_metrics(client, canonical_rsid)
            segs = fetch.fetch_segments(client, canonical_rsid)
            cms = fetch.fetch_calculated_metrics(client, canonical_rsid)
            vrs = fetch.fetch_virtual_report_suites(client, canonical_rsid)
            cls_ds = fetch.fetch_classification_datasets(client, canonical_rsid)
        except ApiError as e:
            print(f"api error: {e}", flush=True)
            return _EXIT_API
        except AaAutoSdrError as e:
            print(f"error: {e}", flush=True)
            return _EXIT_GENERIC

        records.append(
            {
                "rsid": rs.rsid,
                "name": rs.name,
                "timezone": rs.timezone,
                "currency": rs.currency,
                "parent_rsid": rs.parent_rsid,
                "dimensions": len(dims),
                "metrics": len(mets),
                "segments": len(segs),
                "calculated_metrics": len(cms),
                "virtual_report_suites": len(vrs),
                "classifications": len(cls_ds),
            }
        )

    return render_records(
        records,
        format_name=format_name,
        output=_resolve_output(output),
        columns=_DESCRIBE_COLS,
    )
