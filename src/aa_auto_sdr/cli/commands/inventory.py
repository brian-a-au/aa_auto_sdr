"""--inventory-summary handler: cross-RSID aggregate rollup.

Produces totals/min/max/avg across the supplied report suites.
Reuses the v1.7.2 count_only fetcher path — single SDK round-trip
per RSID per component-type.

Output format dispatch supports table | json | csv.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import time
from io import StringIO
from typing import Any

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.cli.list_output import build_footer
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    AmbiguousMatchError,
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode

logger = logging.getLogger(__name__)

_VALID_FORMATS = ("table", "json", "csv")
_COMPONENT_TYPES = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
)


def _aggregate(per_rsid_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute totals/min/max/avg per component type across the supplied rows.

    Empty input returns the zero-shape dict (all counts 0). Single-row input
    yields totals == min == max == avg. avg is rounded to one decimal place
    so table renders cleanly without breaking JSON consumers.
    """
    if not per_rsid_rows:
        return {
            "report_suites_count": 0,
            "totals": dict.fromkeys(_COMPONENT_TYPES, 0),
            "min": dict.fromkeys(_COMPONENT_TYPES, 0),
            "max": dict.fromkeys(_COMPONENT_TYPES, 0),
            "avg": dict.fromkeys(_COMPONENT_TYPES, 0.0),
        }
    n = len(per_rsid_rows)
    totals = {ct: sum(row["counts"][ct] for row in per_rsid_rows) for ct in _COMPONENT_TYPES}
    return {
        "report_suites_count": n,
        "totals": totals,
        "min": {ct: min(row["counts"][ct] for row in per_rsid_rows) for ct in _COMPONENT_TYPES},
        "max": {ct: max(row["counts"][ct] for row in per_rsid_rows) for ct in _COMPONENT_TYPES},
        "avg": {ct: round(totals[ct] / n, 1) for ct in _COMPONENT_TYPES},
    }


def run(
    *,
    rsids: list[str],
    profile: str | None,
    format_name: str | None,
    retry_policy: RetryPolicy | None = None,
    name_match: str = "insensitive",
) -> int:
    started_ms = time.monotonic()
    logger.info("command_start command=inventory", extra={"command": "inventory"})
    exit_code = ExitCode.GENERIC.value
    try:
        fmt = format_name or "table"
        if fmt not in _VALID_FORMATS:
            print(
                f"error: --inventory-summary format must be table|json|csv (got '{fmt}')",
                flush=True,
            )
            exit_code = ExitCode.OUTPUT.value
            return exit_code

        try:
            creds = credentials.resolve(profile=profile)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code

        try:
            client = AaClient.from_credentials(creds, retry_policy=retry_policy)
        except AuthError as exc:
            print(f"auth error: {exc}", flush=True)
            exit_code = ExitCode.AUTH.value
            return exit_code

        # Resolve identifiers (or list all visible RSes when none given).
        canonical: list[str] = []
        if rsids:
            for ident in rsids:
                try:
                    resolved, _ = fetch.resolve_rsid(client, ident, name_match=name_match)
                    canonical.extend(resolved)
                except AmbiguousMatchError as exc:
                    print(
                        f"error: identifier '{ident}' is ambiguous; matched {len(exc.candidates)} report suites:",
                        file=sys.stderr,
                    )
                    for cand_rsid, cand_name in exc.candidates:
                        print(f"  - {cand_rsid}  ({cand_name})", file=sys.stderr)
                    print(
                        "Use a more specific identifier or pass `--name-match exact` (or the rsid directly).",
                        file=sys.stderr,
                    )
                    exit_code = ExitCode.NOT_FOUND.value
                    return exit_code
                except ReportSuiteNotFoundError as exc:
                    print(f"error: {exc}", flush=True)
                    exit_code = ExitCode.NOT_FOUND.value
                    return exit_code
                except ApiError as exc:
                    print(f"api error: {exc}", flush=True)
                    exit_code = ExitCode.API.value
                    return exit_code
        else:
            try:
                canonical = [s.rsid for s in fetch.fetch_report_suite_summaries(client)]
            except ApiError as exc:
                print(f"api error: {exc}", flush=True)
                exit_code = ExitCode.API.value
                return exit_code

        rows: list[dict[str, Any]] = []
        for r in canonical:
            try:
                rs = fetch.fetch_report_suite(client, r)
                vrs_outcome = fetch.fetch_virtual_report_suites(client, r, count_only=True)
                cls_outcome = fetch.fetch_classification_datasets(client, r, count_only=True)
                counts = {
                    "dimensions": len(fetch.fetch_dimensions(client, r)),
                    "metrics": len(fetch.fetch_metrics(client, r)),
                    "segments": len(fetch.fetch_segments(client, r)),
                    "calculated_metrics": len(fetch.fetch_calculated_metrics(client, r)),
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
                row: dict[str, Any] = {"rsid": rs.rsid, "name": rs.name, "counts": counts}
                if fetch_status:
                    row["fetch_status"] = fetch_status
                rows.append(row)
            except ApiError as exc:
                print(f"api error on {r}: {exc}", flush=True)
                exit_code = ExitCode.API.value
                return exit_code

        summary = _aggregate(rows)

        if fmt == "json":
            payload = {
                **summary,
                "per_rsid": rows,
            }
            sys.stdout.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        elif fmt == "csv":
            _emit_csv(rows, summary)
        else:
            _print_table(rows, summary)
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=inventory exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "inventory",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _print_table(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    n = summary["report_suites_count"]
    print(f"INVENTORY SUMMARY ({n} report suites)")
    print("=" * 36)
    print(f"{'Component':<22}  {'Total':>6}  {'Min':>5}  {'Max':>5}  {'Avg':>7}")
    for ct in _COMPONENT_TYPES:
        print(
            f"{ct:<22}  {summary['totals'][ct]:>6}  {summary['min'][ct]:>5}  "
            f"{summary['max'][ct]:>5}  {summary['avg'][ct]:>7}",
        )
    if rows:
        print()
        print("Per-RSID (dim/met/seg/calc/vrs/cls):")
        for row in rows:
            c = row["counts"]
            fs = row.get("fetch_status") or {}
            cells = [f"{c[ct]} *" if ct in fs else str(c[ct]) for ct in _COMPONENT_TYPES]
            label = f"{row['rsid']}  ({row.get('name') or ''})".rstrip()
            print(f"  {label:<40}  {'/'.join(cells)}")
    footer = build_footer(rows)
    if footer:
        print()
        for line in footer:
            print(line)


def _emit_csv(rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["rsid", "name", *_COMPONENT_TYPES])
    for row in rows:
        c = row["counts"]
        writer.writerow([row["rsid"], row.get("name") or "", *(c[ct] for ct in _COMPONENT_TYPES)])
    writer.writerow(["TOTAL", "", *(summary["totals"][ct] for ct in _COMPONENT_TYPES)])
    sys.stdout.write(buf.getvalue())
