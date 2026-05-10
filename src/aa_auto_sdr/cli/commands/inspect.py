"""Inspect command handlers: per-component listing + per-RS describe.

Each list-X command resolves the identifier (RSID or name), runs the relevant
fetcher across resolved RSIDs (multi-match-by-name produces one record-set per
RSID with a disambiguating 'rsid' column), applies filter/sort/limit, renders.

run_describe_reportsuite returns metadata + counts (no full SDR generated)."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.models import FetchStatus
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.cli._filters import apply_filters
from aa_auto_sdr.cli.list_output import annotate_cells, build_footer, render_records
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    AaAutoSdrError,
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode

logger = logging.getLogger(__name__)

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
_DESCRIBE_COLS_TABULAR = [
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
# Same columns plus the structured fetch-status field; used for JSON output only.
_DESCRIBE_COLS_JSON = [*_DESCRIBE_COLS_TABULAR, "fetch_status"]

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


def _bootstrap(
    profile: str | None,
    *,
    retry_policy: RetryPolicy | None = None,
) -> tuple[AaClient | None, int]:
    """Resolve credentials and build a client. Returns (client, 0) on success
    or (None, exit_code) on failure."""
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return None, ExitCode.CONFIG.value

    try:
        client = AaClient.from_credentials(creds, retry_policy=retry_policy)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return None, ExitCode.AUTH.value
    return client, ExitCode.OK.value


def _list_per_component(
    *,
    command: str,
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
    retry_policy: RetryPolicy | None = None,
    name_match: str = "insensitive",  # v1.9.0
) -> int:
    """Generic list-X handler: resolve identifier → fetch per RSID → flatten →
    filter → render. Pattern 9B.3 — one start/complete pair covers all five
    list-X entry points (each passes its own ``command`` value)."""
    started_ms = time.monotonic()
    logger.info("command_start command=%s", command, extra={"command": command})
    exit_code = ExitCode.GENERIC.value
    try:
        client, rc = _bootstrap(profile, retry_policy=retry_policy)
        if client is None:
            exit_code = rc
            return exit_code

        try:
            canonical_rsids, _was_name = fetch.resolve_rsid(client, identifier, name_match=name_match)
        except ReportSuiteNotFoundError as e:
            print(f"error: {e}", flush=True)
            exit_code = ExitCode.NOT_FOUND.value
            return exit_code
        except ApiError as e:
            print(f"api error: {e}", flush=True)
            exit_code = ExitCode.API.value
            return exit_code

        multi = len(canonical_rsids) > 1
        if multi:
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
                exit_code = ExitCode.API.value
                return exit_code
            except AaAutoSdrError as e:
                print(f"error: {e}", flush=True)
                exit_code = ExitCode.GENERIC.value
                return exit_code
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
            exit_code = ExitCode.USAGE.value
            return exit_code

        exit_code = render_records(
            filtered,
            format_name=format_name,
            output=_resolve_output(output),
            columns=cols,
        )
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=%s exit_code=%s duration_ms=%s",
            command,
            exit_code,
            duration_ms,
            extra={
                "command": command,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def run_list_metrics(**kwargs: Any) -> int:
    return _list_per_component(
        command="list_metrics",
        fetcher=fetch.fetch_metrics,
        columns=_METRIC_COLS,
        sort_allowlist=_METRIC_SORT,
        **kwargs,
    )


def run_list_dimensions(**kwargs: Any) -> int:
    return _list_per_component(
        command="list_dimensions",
        fetcher=fetch.fetch_dimensions,
        columns=_DIMENSION_COLS,
        sort_allowlist=_DIMENSION_SORT,
        **kwargs,
    )


def run_list_segments(**kwargs: Any) -> int:
    return _list_per_component(
        command="list_segments",
        fetcher=fetch.fetch_segments,
        columns=_SEGMENT_COLS,
        sort_allowlist=_SEGMENT_SORT,
        **kwargs,
    )


def run_list_calculated_metrics(**kwargs: Any) -> int:
    return _list_per_component(
        command="list_calculated_metrics",
        fetcher=fetch.fetch_calculated_metrics,
        columns=_CALCULATED_COLS,
        sort_allowlist=_CALCULATED_SORT,
        **kwargs,
    )


def run_list_classification_datasets(**kwargs: Any) -> int:
    # Capture status as a side effect via closure so _list_per_component's
    # generic contract (fetcher: (client, rsid) -> list[T]) stays unchanged.
    # Raw (status, expansion_level) tuple is enough for the banner — no need
    # for the formal FetchOutcomeMeta dataclass for an internal capture.
    captured_status: dict[str, tuple[FetchStatus, str | None]] = {}

    def _fetcher(client: Any, rsid: str) -> Any:
        outcome = fetch.fetch_classification_datasets(client, rsid)
        if outcome.status != "healthy":
            captured_status[rsid] = (outcome.status, outcome.expansion_level)
        return outcome.data

    rc = _list_per_component(
        command="list_classification_datasets",
        fetcher=_fetcher,
        columns=_CLASSIFICATION_COLS,
        sort_allowlist=_CLASSIFICATION_SORT,
        **kwargs,
    )

    # After the list renders, emit one stderr banner per non-healthy RSID.
    # Exit code unchanged — banner is informational; preserves pipeline UX.
    for rsid, (status, expansion_level) in captured_status.items():
        if status == "degraded":
            print(
                f"⚠ classifications fetch degraded for {rsid} — list may be incomplete; see logs/SDR_*.log",
                file=sys.stderr,
                flush=True,
            )
        elif status == "partial":
            print(
                f"⚠ classifications fetch partial for {rsid} (expansion_level={expansion_level}); see logs/SDR_*.log",
                file=sys.stderr,
                flush=True,
            )
    return rc


def run_describe_reportsuite(
    *,
    identifier: str,
    profile: str | None,
    format_name: str | None,
    output: str | None,
    retry_policy: RetryPolicy | None = None,
    name_match: str = "insensitive",  # v1.9.0
) -> int:
    """Print metadata + per-component counts for one RS (or several on multi-match)."""
    started_ms = time.monotonic()
    logger.info(
        "command_start command=describe_reportsuite",
        extra={"command": "describe_reportsuite"},
    )
    exit_code = ExitCode.GENERIC.value
    try:
        client, rc = _bootstrap(profile, retry_policy=retry_policy)
        if client is None:
            exit_code = rc
            return exit_code

        try:
            canonical_rsids, _was_name = fetch.resolve_rsid(client, identifier, name_match=name_match)
        except ReportSuiteNotFoundError as e:
            print(f"error: {e}", flush=True)
            exit_code = ExitCode.NOT_FOUND.value
            return exit_code
        except ApiError as e:
            print(f"api error: {e}", flush=True)
            exit_code = ExitCode.API.value
            return exit_code

        records: list[dict[str, Any]] = []
        for canonical_rsid in canonical_rsids:
            try:
                rs = fetch.fetch_report_suite(client, canonical_rsid)
                dims = fetch.fetch_dimensions(client, canonical_rsid)
                mets = fetch.fetch_metrics(client, canonical_rsid)
                segs = fetch.fetch_segments(client, canonical_rsid)
                cms = fetch.fetch_calculated_metrics(client, canonical_rsid)
                vrs_outcome = fetch.fetch_virtual_report_suites(
                    client,
                    canonical_rsid,
                    count_only=True,
                )
                cls_outcome = fetch.fetch_classification_datasets(
                    client,
                    canonical_rsid,
                    count_only=True,
                )
            except ApiError as e:
                print(f"api error: {e}", flush=True)
                exit_code = ExitCode.API.value
                return exit_code
            except AaAutoSdrError as e:
                print(f"error: {e}", flush=True)
                exit_code = ExitCode.GENERIC.value
                return exit_code

            record: dict[str, Any] = {
                "rsid": rs.rsid,
                "name": rs.name,
                "timezone": rs.timezone,
                "currency": rs.currency,
                "parent_rsid": rs.parent_rsid,
                "dimensions": len(dims),
                "metrics": len(mets),
                "segments": len(segs),
                "calculated_metrics": len(cms),
                "virtual_report_suites": len(vrs_outcome.data),
                "classifications": len(cls_outcome.data),
            }
            fetch_status: dict[str, dict[str, Any]] = {}
            if vrs_outcome.status != "healthy":
                fetch_status["virtual_report_suites"] = {
                    "status": vrs_outcome.status,
                    "expansion_level": vrs_outcome.expansion_level,
                }
            if cls_outcome.status != "healthy":
                fetch_status["classifications"] = {
                    "status": cls_outcome.status,
                    "expansion_level": cls_outcome.expansion_level,
                }
            if fetch_status:
                record["fetch_status"] = fetch_status
            records.append(record)

        # Format-aware rendering. JSON path emits fetch_status field only when at
        # least one record is non-healthy; tabular path uses cell asterisks +
        # footer; CSV path strips fetch_status entirely.
        has_non_healthy = any("fetch_status" in r for r in records)
        if format_name == "json":
            cols = _DESCRIBE_COLS_JSON if has_non_healthy else _DESCRIBE_COLS_TABULAR
            records_for_render = records
            footers = None
        else:
            cols = _DESCRIBE_COLS_TABULAR
            if format_name is None:  # implicit-table
                records_for_render = annotate_cells(records)
                footers = build_footer(records)
            else:  # csv
                records_for_render = records
                footers = None

        exit_code = render_records(
            records_for_render,
            format_name=format_name,
            output=_resolve_output(output),
            columns=cols,
            footers=footers,
        )
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=describe_reportsuite exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "describe_reportsuite",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )
