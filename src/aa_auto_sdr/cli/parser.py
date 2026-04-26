"""Argparse surface for v0.3.

Action flags are mutually exclusive — one action per invocation. Common options
(--filter, --exclude, --sort, --limit, --format, --output, --output-dir,
--profile) are universally accepted; semantics depend on the action."""

from __future__ import annotations

import argparse
from pathlib import Path

# Generate command supports all 5 formats + 4 aliases
_GENERATE_FORMATS = [
    "excel",
    "csv",
    "json",
    "html",
    "markdown",
    "all",
    "reports",
    "data",
    "ci",
]
# List/inspect commands: strict CJA parity — only json|csv (no markdown for lists)
_LIST_FORMATS = ["json", "csv"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aa_auto_sdr",
        description="Adobe Analytics SDR Generator (API 2.0 only)",
    )

    # Action flags (mutually exclusive). Positional RSID is also an action;
    # we enforce mutual exclusion via post-parse dispatch since argparse can't
    # put a positional in an exclusive group cleanly.
    actions = p.add_mutually_exclusive_group()
    actions.add_argument(
        "--list-reportsuites",
        action="store_true",
        help="List all report suites visible to the org",
    )
    actions.add_argument(
        "--list-virtual-reportsuites",
        action="store_true",
        help="List all virtual report suites",
    )
    actions.add_argument(
        "--describe-reportsuite",
        metavar="RSID_OR_NAME",
        default=None,
        help="Print metadata + per-component counts for one report suite",
    )
    actions.add_argument(
        "--list-metrics",
        metavar="RSID_OR_NAME",
        default=None,
        help="List metrics for one report suite",
    )
    actions.add_argument(
        "--list-dimensions",
        metavar="RSID_OR_NAME",
        default=None,
        help="List dimensions for one report suite",
    )
    actions.add_argument(
        "--list-segments",
        metavar="RSID_OR_NAME",
        default=None,
        help="List segments for one report suite",
    )
    actions.add_argument(
        "--list-calculated-metrics",
        metavar="RSID_OR_NAME",
        default=None,
        help="List calculated metrics for one report suite",
    )
    actions.add_argument(
        "--list-classification-datasets",
        metavar="RSID_OR_NAME",
        default=None,
        help="List classification datasets for one report suite",
    )
    actions.add_argument(
        "--profile-add",
        metavar="NAME",
        default=None,
        help="Create or update a credentials profile interactively",
    )
    actions.add_argument(
        "--show-config",
        action="store_true",
        help="Print which credential source resolved and exit",
    )

    # Positional RSID for generate
    p.add_argument(
        "rsid",
        nargs="?",
        default=None,
        help="Report Suite ID or name to generate an SDR for",
    )

    # Common options
    p.add_argument(
        "--filter",
        default=None,
        metavar="STR",
        help="Case-insensitive substring match on `name` (list/inspect only)",
    )
    p.add_argument(
        "--exclude",
        default=None,
        metavar="STR",
        help="Case-insensitive substring exclusion on `name` (list/inspect only)",
    )
    p.add_argument(
        "--sort",
        default=None,
        metavar="FIELD",
        help="Sort field (list/inspect only; allowlist per command)",
    )
    p.add_argument(
        "--limit",
        default=None,
        type=int,
        metavar="N",
        help="Cap output to N records (list/inspect only; N>=0)",
    )

    # Format — generate-format and list-format share the same flag.
    # Validation deferred to handlers (different allowlists per action).
    p.add_argument(
        "--format",
        default=None,
        metavar="FMT",
        help=(
            "Generate: excel|csv|json|html|markdown|all|reports|data|ci. "
            "List/inspect: json|csv (default = fixed-width table to stdout)."
        ),
    )

    # Output destinations
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory to write SDR generation outputs into (default: cwd)",
    )
    p.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="Output path for list/inspect commands. '-' = stdout pipe.",
    )

    # Auth
    p.add_argument(
        "--profile",
        default=None,
        help="Use a named credentials profile from ~/.aa/orgs/<name>/",
    )

    return p
