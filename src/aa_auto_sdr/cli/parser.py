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
        "--batch",
        nargs="+",
        metavar="RSID_OR_NAME",
        default=None,
        help="Generate SDRs for multiple report suites sequentially (continue on error)",
    )
    actions.add_argument(
        "--diff",
        nargs=2,
        metavar=("A", "B"),
        default=None,
        help="Diff two snapshots. Tokens: <path> | <rsid>@<ts>|@latest|@previous | git:<ref>:<path>",
    )
    actions.add_argument(
        "--exit-codes",
        action="store_true",
        help="List every exit code with a one-line meaning",
    )
    actions.add_argument(
        "--explain-exit-code",
        metavar="CODE",
        type=int,
        default=None,
        help="Print the meaning, likely causes, and remediation for an exit code",
    )
    actions.add_argument(
        "--completion",
        choices=("bash", "zsh", "fish"),
        default=None,
        help="Emit a shell completion script (redirect to your shell's completion dir)",
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
    actions.add_argument(
        "--list-snapshots",
        action="store_true",
        help="List snapshots in ~/.aa/orgs/<profile>/snapshots/ (requires --profile; pass <RSID> positional to filter)",
    )
    actions.add_argument(
        "--prune-snapshots",
        action="store_true",
        help="Apply retention policy and delete snapshots (requires --profile + --keep-last|--keep-since; pass <RSID> positional to scope to one)",
    )
    actions.add_argument(
        "--profile-list",
        action="store_true",
        help="List all credentials profiles in ~/.aa/orgs/",
    )
    actions.add_argument(
        "--profile-test",
        metavar="NAME",
        default=None,
        help="Authenticate the named profile (OAuth + getCompanyId), print PASS/FAIL",
    )
    actions.add_argument(
        "--profile-show",
        metavar="NAME",
        default=None,
        help="Show profile fields with masked client_id (no secret)",
    )
    actions.add_argument(
        "--profile-import",
        nargs=2,
        metavar=("NAME", "FILE"),
        default=None,
        help="Import a JSON file as a credentials profile",
    )

    # Positional RSID(s) — one or more. Single value runs generate; multiple values
    # auto-batch (sequential, continue-on-error). RSIDs and names may be mixed freely.
    # Also accepts an optional single RSID filter for --list-snapshots / --prune-snapshots.
    p.add_argument(
        "rsids",
        nargs="*",
        default=[],
        metavar="RSID_OR_NAME",
        help=(
            "One or more report suites (RSID or case-insensitive name). "
            "Multiple values auto-batch (sequential, continue-on-error). "
            "RSIDs and names may be mixed freely."
        ),
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
            "List/inspect: json|csv (default = fixed-width table to stdout). "
            "Diff: console|json|markdown|pr-comment."
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

    # Snapshot persistence (v0.7)
    p.add_argument(
        "--snapshot",
        action="store_true",
        help="Persist the built SdrDocument to ~/.aa/orgs/<profile>/snapshots/<RSID>/<ts>.json (requires --profile)",
    )

    # v1.1 — auto-snapshot + retention
    p.add_argument(
        "--auto-snapshot",
        action="store_true",
        help="On generate/batch, save a snapshot per RSID (requires --profile)",
    )
    p.add_argument(
        "--auto-prune",
        action="store_true",
        help="After auto-snapshot or with --prune-snapshots, apply retention policy",
    )
    keep_group = p.add_mutually_exclusive_group()
    keep_group.add_argument(
        "--keep-last",
        type=int,
        default=None,
        metavar="N",
        help="Retention: keep N most recent snapshots per RSID",
    )
    keep_group.add_argument(
        "--keep-since",
        default=None,
        metavar="DURATION",
        help="Retention: keep snapshots newer than DURATION (e.g. 30d, 12h, 4w)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="For --prune-snapshots, list deletions without unlinking",
    )

    # v1.1 — diff modifiers
    p.add_argument(
        "--side-by-side",
        action="store_true",
        help="Render diff modified-component fields side-by-side (console/markdown only)",
    )
    p.add_argument(
        "--summary",
        action="store_true",
        help="Render diff as count-only summary (no per-field detail)",
    )
    p.add_argument(
        "--ignore-fields",
        default=None,
        metavar="CSV",
        help="Comma-separated field names to skip during compare (e.g. description,tags)",
    )

    return p
