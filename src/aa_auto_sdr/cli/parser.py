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
    actions.add_argument(
        "--stats",
        action="store_true",
        help="Quick component counts per RSID (no full SDR build)",
    )
    actions.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively pick an RSID from --list-reportsuites; emits to stdout",
    )
    actions.add_argument(
        "--config-status",
        action="store_true",
        help="Print full credential resolution chain (more verbose than --show-config)",
    )
    actions.add_argument(
        "--validate-config",
        action="store_true",
        help="Resolve and validate credential shape WITHOUT calling Adobe",
    )
    actions.add_argument(
        "--sample-config",
        action="store_true",
        help="Emit a config.json template to stdout",
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
        help=(
            "Preview without writing: for --prune-snapshots list deletions; "
            "for <RSID> / --batch list output paths (auth still happens, no "
            "component fetch, no files written)"
        ),
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

    # v1.2 — diff polish
    p.add_argument(
        "--quiet-diff",
        action="store_true",
        help="Suppress unchanged trailers; show only changed sections",
    )
    p.add_argument(
        "--diff-labels",
        nargs=2,
        default=None,
        metavar=("A=LABEL_A", "B=LABEL_B"),
        help="Override Source/Target labels (e.g. A=baseline B=candidate)",
    )
    p.add_argument(
        "--reverse-diff",
        action="store_true",
        help="Swap a and b before compare",
    )
    p.add_argument(
        "--warn-threshold",
        type=int,
        default=None,
        metavar="N",
        help="Exit code 3 if total changes >= N",
    )
    p.add_argument(
        "--changes-only",
        action="store_true",
        help="In rendered diff, drop component types with no changes",
    )
    p.add_argument(
        "--show-only",
        default=None,
        metavar="TYPES",
        help="Restrict diff output to listed component types (CSV)",
    )
    p.add_argument(
        "--max-issues",
        type=int,
        default=None,
        metavar="N",
        help="Cap each component's added/removed/modified to N items in render",
    )

    # v1.2 — generation modifiers
    gen_modifiers = p.add_mutually_exclusive_group()
    gen_modifiers.add_argument(
        "--metrics-only",
        action="store_true",
        help="Generate SDR with only metrics",
    )
    gen_modifiers.add_argument(
        "--dimensions-only",
        action="store_true",
        help="Generate SDR with only dimensions",
    )

    # v1.2 — UX gates
    p.add_argument(
        "--open",
        action="store_true",
        help="Open the generated output in the OS default app after writing",
    )
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        dest="yes",
        help="Skip confirmation prompts (for --prune-snapshots, etc.)",
    )
    p.add_argument(
        "--profile-overwrite",
        action="store_true",
        help="Allow --profile-import to overwrite an existing profile",
    )

    # v1.2.1 — observability
    p.add_argument(
        "--show-timings",
        action="store_true",
        help="Print per-stage timings at end of run (auth, resolve, build, write)",
    )

    return p
