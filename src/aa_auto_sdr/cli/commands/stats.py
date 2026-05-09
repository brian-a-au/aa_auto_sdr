"""--stats handler: per-RSID component counts.

Lighter than --describe-reportsuite — only counts, no metadata. Lists every
visible RSID when no positional arg is given."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.cli.list_output import build_footer
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode

logger = logging.getLogger(__name__)

_VALID_FORMATS = ("table", "json")


def run(
    *,
    rsids: list[str],
    profile: str | None,
    format_name: str | None,
    retry_policy: RetryPolicy | None = None,
) -> int:
    started_ms = time.monotonic()
    logger.info("command_start command=stats", extra={"command": "stats"})
    exit_code = ExitCode.GENERIC.value
    try:
        fmt = format_name or "table"
        if fmt not in _VALID_FORMATS:
            print(
                f"error: --stats format must be json|table (got '{fmt}')",
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
            try:
                for ident in rsids:
                    resolved, _ = fetch.resolve_rsid(client, ident)
                    canonical.extend(resolved)
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

        rows: list[dict] = []
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
                row: dict = {"rsid": rs.rsid, "name": rs.name, "counts": counts}
                if fetch_status:
                    row["fetch_status"] = fetch_status
                rows.append(row)
            except ApiError as exc:
                print(f"api error on {r}: {exc}", flush=True)
                exit_code = ExitCode.API.value
                return exit_code

        if fmt == "json":
            sys.stdout.write(json.dumps(rows, sort_keys=True, indent=2) + "\n")
        else:
            _print_table(rows)
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=stats exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "stats",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def _print_table(rows: list[dict]) -> None:
    header = f"{'RSID':<24}  {'NAME':<30}  {'DIM':>5}  {'MET':>5}  {'SEG':>5}  {'CALC':>5}  {'VRS':>5}  {'CLS':>5}"
    print(header)
    for r in rows:
        c = r["counts"]
        fs = r.get("fetch_status") or {}
        # Build a copy of counts with asterisk markers for non-healthy components.
        cells: dict = dict(c)
        for ct in fs:
            if ct in cells:
                cells[ct] = f"{cells[ct]} *"
        name = (r.get("name") or "")[:30]
        print(
            f"{r['rsid']:<24}  {name:<30}  {cells['dimensions']:>5}  {cells['metrics']:>5}  "
            f"{cells['segments']:>5}  {cells['calculated_metrics']:>5}  "
            f"{cells['virtual_report_suites']:>5}  {cells['classifications']:>5}",
        )
    # Footer: derived from each row's fetch_status field via the shared helper.
    footer = build_footer(rows)
    if footer:
        print()  # blank line separates table from footer
        for line in footer:
            print(line)
