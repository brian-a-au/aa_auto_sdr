"""--stats handler: per-RSID component counts.

Lighter than --describe-reportsuite — only counts, no metadata. Lists every
visible RSID when no positional arg is given."""

from __future__ import annotations

import json
import sys

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    ApiError,
    AuthError,
    ConfigError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode

_VALID_FORMATS = ("table", "json")


def run(*, rsids: list[str], profile: str | None, format_name: str | None) -> int:
    fmt = format_name or "table"
    if fmt not in _VALID_FORMATS:
        print(
            f"error: --stats format must be json|table (got '{fmt}')",
            flush=True,
        )
        return ExitCode.OUTPUT.value

    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as exc:
        print(f"error: {exc}", flush=True)
        return ExitCode.CONFIG.value

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as exc:
        print(f"auth error: {exc}", flush=True)
        return ExitCode.AUTH.value

    # Resolve identifiers (or list all visible RSes when none given).
    canonical: list[str] = []
    if rsids:
        try:
            for ident in rsids:
                resolved, _ = fetch.resolve_rsid(client, ident)
                canonical.extend(resolved)
        except ReportSuiteNotFoundError as exc:
            print(f"error: {exc}", flush=True)
            return ExitCode.NOT_FOUND.value
        except ApiError as exc:
            print(f"api error: {exc}", flush=True)
            return ExitCode.API.value
    else:
        try:
            canonical = [s.rsid for s in fetch.fetch_report_suite_summaries(client)]
        except ApiError as exc:
            print(f"api error: {exc}", flush=True)
            return ExitCode.API.value

    rows: list[dict] = []
    for r in canonical:
        try:
            rs = fetch.fetch_report_suite(client, r)
            counts = {
                "dimensions": len(fetch.fetch_dimensions(client, r)),
                "metrics": len(fetch.fetch_metrics(client, r)),
                "segments": len(fetch.fetch_segments(client, r)),
                "calculated_metrics": len(fetch.fetch_calculated_metrics(client, r)),
                "virtual_report_suites": len(fetch.fetch_virtual_report_suites(client, r)),
                "classifications": len(fetch.fetch_classification_datasets(client, r)),
            }
            rows.append({"rsid": rs.rsid, "name": rs.name, "counts": counts})
        except ApiError as exc:
            print(f"api error on {r}: {exc}", flush=True)
            return ExitCode.API.value

    if fmt == "json":
        sys.stdout.write(json.dumps(rows, sort_keys=True, indent=2) + "\n")
    else:
        _print_table(rows)
    return ExitCode.OK.value


def _print_table(rows: list[dict]) -> None:
    header = f"{'RSID':<24}  {'NAME':<30}  {'DIM':>5}  {'MET':>5}  {'SEG':>5}  {'CALC':>5}  {'VRS':>5}  {'CLS':>5}"
    print(header)
    for r in rows:
        c = r["counts"]
        name = (r.get("name") or "")[:30]
        print(
            f"{r['rsid']:<24}  {name:<30}  {c['dimensions']:>5}  {c['metrics']:>5}  "
            f"{c['segments']:>5}  {c['calculated_metrics']:>5}  "
            f"{c['virtual_report_suites']:>5}  {c['classifications']:>5}",
        )
