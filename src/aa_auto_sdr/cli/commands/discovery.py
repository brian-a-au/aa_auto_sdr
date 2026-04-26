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

_EXIT_OK = 0
_EXIT_GENERIC = 1
_EXIT_USAGE = 2
_EXIT_CONFIG = 10
_EXIT_AUTH = 11
_EXIT_API = 12

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
        return _EXIT_CONFIG

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return _EXIT_AUTH

    try:
        suites = fetch._records(client.handle.getReportSuites(extended_info=True))
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API
    except AaAutoSdrError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_GENERIC

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
        return _EXIT_CONFIG

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return _EXIT_AUTH

    try:
        raws = fetch._records(client.handle.getVirtualReportSuites(extended_info=True))
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API
    except AaAutoSdrError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_GENERIC

    # Normalize parentRsid -> parent_rsid for sort allowlist consistency
    normalized = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "parent_rsid": r.get("parentRsid", ""),
        }
        for r in raws
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
        return _EXIT_USAGE

    return render_records(
        filtered,
        format_name=format_name,
        output=_resolve_output(output),
        columns=columns,
    )
