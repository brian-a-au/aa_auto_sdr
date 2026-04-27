"""Discovery command handlers: --list-reportsuites, --list-virtual-reportsuites.

Both call into the AA SDK, normalize the response shape, run filter/sort/limit,
and render via list_output."""

from __future__ import annotations

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
)
from aa_auto_sdr.core.exit_codes import ExitCode

_REPORTSUITES_SORT_ALLOWLIST = ("rsid", "name")
_VRS_SORT_ALLOWLIST = ("id", "name", "parent_rsid")


def _resolve_output(output: str | None) -> Path | None:
    if output is None:
        return None
    if output == "-":
        return Path("-")
    return Path(output)


def run_list_reportsuites(
    *,
    profile: str | None,
    format_name: str | None,
    output: str | None,
    name_filter: str | None,
    name_exclude: str | None,
    sort_field: str | None,
    limit: int | None,
) -> int:
    """List all report suites visible to the org."""
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.CONFIG.value

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return ExitCode.AUTH.value

    try:
        summaries = fetch.fetch_report_suite_summaries(client)
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return ExitCode.API.value
    except AaAutoSdrError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.GENERIC.value
    # Convert to dicts for the existing renderer (which expects dict-shaped rows).
    suites = [{"rsid": s.rsid, "name": s.name or ""} for s in summaries]

    return _render_with_filters(
        suites,
        sort_allowlist=_REPORTSUITES_SORT_ALLOWLIST,
        format_name=format_name,
        output=output,
        name_filter=name_filter,
        name_exclude=name_exclude,
        sort_field=sort_field,
        limit=limit,
        columns=["rsid", "name"],
    )


def run_list_virtual_reportsuites(
    *,
    profile: str | None,
    format_name: str | None,
    output: str | None,
    name_filter: str | None,
    name_exclude: str | None,
    sort_field: str | None,
    limit: int | None,
) -> int:
    """List all virtual report suites."""
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.CONFIG.value

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return ExitCode.AUTH.value

    try:
        summaries = fetch.fetch_virtual_report_suite_summaries(client)
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return ExitCode.API.value
    except AaAutoSdrError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.GENERIC.value
    # Convert to dicts for the existing renderer (which expects dict-shaped rows).
    normalized = [
        {"id": s.id, "name": s.name or "", "parent_rsid": s.parent_rsid}
        for s in summaries
    ]

    return _render_with_filters(
        normalized,
        sort_allowlist=_VRS_SORT_ALLOWLIST,
        format_name=format_name,
        output=output,
        name_filter=name_filter,
        name_exclude=name_exclude,
        sort_field=sort_field,
        limit=limit,
        columns=["id", "name", "parent_rsid"],
    )


def _render_with_filters(
    records: list[dict[str, Any]],
    *,
    sort_allowlist: tuple[str, ...],
    format_name: str | None,
    output: str | None,
    name_filter: str | None,
    name_exclude: str | None,
    sort_field: str | None,
    limit: int | None,
    columns: list[str],
) -> int:
    """Apply filters, then render. Catches ValueError from apply_filters."""
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
        return ExitCode.USAGE.value

    return render_records(
        filtered,
        format_name=format_name,
        output=_resolve_output(output),
        columns=columns,
    )
