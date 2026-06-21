"""Argparse surface for v0.3.

Action flags are mutually exclusive — one action per invocation. Common options
(--filter, --exclude, --sort, --limit, --format, --output, --output-dir,
--profile) are universally accepted; semantics depend on the action."""

from __future__ import annotations

import argparse
from pathlib import Path

from aa_auto_sdr.cli.option_resolution import explicit_long_option_dests

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

_AGENT_MODE_DEFAULTS: dict[str, str] = {
    "format": "json",
    "output": "-",
    "log_format": "json",
}


def _non_negative_int(s: str) -> int:
    v = int(s)
    if v < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {v}")
    return v


def _positive_float(s: str) -> float:
    v = float(s)
    if v <= 0:
        raise argparse.ArgumentTypeError(f"must be positive, got {v}")
    return v


def _positive_int(s: str) -> int:
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {v}")
    return v


def _workers_int(s: str) -> int:
    v = _positive_int(s)
    if v > 16:
        raise argparse.ArgumentTypeError(f"--workers must be 1..16, got {v}")
    return v


def _configured_long_options(parser: argparse.ArgumentParser) -> frozenset[str]:
    """Extract all configured long-option strings from an ArgumentParser."""
    options: set[str] = set()
    for action in parser._actions:
        for opt in action.option_strings:
            if opt.startswith("--"):
                options.add(opt)
    return frozenset(options)


def _apply_agent_mode_defaults(
    args: argparse.Namespace,
    argv: list[str] | None,
    *,
    known_long_options: frozenset[str],
) -> None:
    """Apply --agent-mode preset defaults for options not explicitly provided.

    Only sets a default if the corresponding long option is absent from argv.
    The preset never overrides explicit user choices.
    """
    if not getattr(args, "agent_mode", False):
        return

    explicit_dests = explicit_long_option_dests(
        argv,
        tracked_options={"--format", "--output", "--log-format"},
        known_long_options=known_long_options,
    )
    for dest, default_value in _AGENT_MODE_DEFAULTS.items():
        if dest not in explicit_dests:
            setattr(args, dest, default_value)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aa_auto_sdr",
        description="Adobe Analytics SDR Generator (API 2.0 only)",
        # v1.6.0 — disable argparse abbreviation. Abbreviated long options
        # (e.g. ``--forma`` for ``--format``) bypass the explicit-option
        # detector that ``_apply_agent_mode_defaults`` relies on, which
        # would silently overwrite the user's explicit choice with the
        # agent-mode preset's default. Force the canonical long form.
        allow_abbrev=False,
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
        help="List snapshots in the active snapshot dir (requires --profile or --snapshot-dir; pass <RSID> positional to filter)",
    )
    actions.add_argument(
        "--prune-snapshots",
        action="store_true",
        help=(
            "Apply retention policy and delete snapshots (requires --profile or --snapshot-dir, "
            "plus --keep-last|--keep-since; pass <RSID> positional to scope to one; "
            "pass --yes for non-interactive use, otherwise refuses with exit 2)"
        ),
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
        "--inventory-summary",
        action="store_true",
        help="Cross-RSID aggregate rollup of component counts (totals/min/max/avg).",
    )
    actions.add_argument(
        "--trending-window",
        type=str,
        default=None,
        metavar="DURATION",
        help=("Per-RSID drift window (Nh|Nd|Nw, e.g. '30d'). Reads existing snapshots; no API contact (v1.13.0)."),
    )
    actions.add_argument(
        "--compare-with-prev",
        action="store_true",
        help=(
            "Diff a report suite's latest snapshot vs the immediately previous one. "
            "Sugar for --diff <RSID>@previous <RSID>@latest (v1.13.0)."
        ),
    )
    actions.add_argument(
        "--watch",
        action="store_true",
        help=(
            "Enter watch mode: loop over the positional RSID(s) at --interval, "
            "snapshot + diff each cycle, emit NDJSON events to stdout. "
            "SIGINT to stop. (v1.14.0)"
        ),
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
            "(--template auto-routes 'excel' to 'excel-template'.) "
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
        "--snapshot-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Override the active profile's snapshot directory for all snapshot-aware "
            "actions (--snapshot, --diff, --list-snapshots, --prune-snapshots, "
            "--compare-with-prev). Useful for CI / governance contexts where snapshots "
            "live outside ~/.aa/."
        ),
    )
    p.add_argument(
        "--interval",
        type=str,
        default=None,
        metavar="DURATION",
        help="Watch cadence (Nh|Nd|Nw, e.g. '1h'). Required with --watch. (v1.14.0)",
    )
    p.add_argument(
        "--watch-threshold",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Minimum total change count to emit a `change` event. 0 emits every cycle (heartbeat). Default 1. (v1.14.0)"
        ),
    )

    # v1.15.0 — git integration modifiers (NOT in any mutex group)
    p.add_argument(
        "--git-commit",
        action="store_true",
        help=(
            "After saving a snapshot, commit it to the snapshot dir's git repo. "
            "Auto-inits the dir as a git repo on first use. (v1.15.0)"
        ),
    )
    p.add_argument(
        "--git-push",
        action="store_true",
        help="Push after a successful --git-commit. Requires --git-commit. (v1.15.0)",
    )
    p.add_argument(
        "--git-message",
        type=str,
        default=None,
        metavar="TEXT",
        help="Override the auto-generated commit message. Requires --git-commit. (v1.15.0)",
    )

    # v1.16.0 — template-fill modifiers (NOT in any mutex group)
    p.add_argument(
        "--template",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Path to an existing .xlsx template (e.g. Adobe's BRD/SDR template). "
            "Switches the Excel writer to fill mode, preserving styles, formulas, "
            "and untouched cells. (v1.16.0)"
        ),
    )
    p.add_argument(
        "--template-organization",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "Organization name written to Glossary!C2. Defaults to the report suite "
            "name. Requires --template. (v1.16.0)"
        ),
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
    p.add_argument(
        "--run-summary-json",
        default=None,
        metavar="PATH",
        help="Emit a JSON run summary to PATH (or '-' for stdout)",
    )

    # v1.3.0 — logging
    p.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO, or LOG_LEVEL env var)",
    )
    p.add_argument(
        "--log-format",
        type=str,
        default="text",
        choices=["text", "json"],
        help='Log output format: "text" (default, human-readable) or "json" (NDJSON for Splunk/ELK)',
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress progress banners and INFO console output. Errors and final paths still print. Log file is unaffected.",
    )
    p.add_argument(
        "--color-theme",
        type=str,
        choices=["default", "accessible"],
        default="default",
        help="Diff color palette: 'default' (green/red) or 'accessible' (blue/orange — better for red-green deuteranopia)",
    )

    # v1.6.0 — agent integration
    agent_group = p.add_argument_group("Agent Integration")
    agent_group.add_argument(
        "--agent-mode",
        action="store_true",
        default=False,
        help=(
            "Agent-friendly preset: defaults to --format json --output - --log-format json "
            "for options the user did not explicitly pass. --output - implies --quiet "
            "(banner / progress / INFO on stderr suppressed; errors and final result paths still print)."
        ),
    )

    # v1.7.0 — retry tuning
    retry = p.add_argument_group("Retry")
    retry.add_argument(
        "--max-retries",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help="Max retries on transient API failures (429 / 5xx, connection timeout). Default 3.",
    )
    retry.add_argument(
        "--retry-base-delay",
        type=_positive_float,
        default=None,
        metavar="SECONDS",
        help="Base delay for exponential backoff in seconds. Default 0.5.",
    )
    retry.add_argument(
        "--retry-max-delay",
        type=_positive_float,
        default=None,
        metavar="SECONDS",
        help="Maximum delay between retries in seconds. Default 10.0.",
    )

    # v1.8.0 — batch parallelism
    batch_grp = p.add_argument_group("batch parallelism (v1.8.0+)")
    batch_grp.add_argument(
        "--workers",
        type=_workers_int,
        default=1,
        metavar="N",
        help="Number of parallel worker threads for --batch (default: 1, max: 16).",
    )
    batch_grp.add_argument(
        "--fail-fast",
        action="store_true",
        help="In parallel batch mode, cancel pending workers on first failure.",
    )

    # v1.10.0 — batch sampling
    sample_grp = p.add_argument_group("batch sampling (v1.10.0+)")
    sample_grp.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        dest="sample_size",
        help="Subset N RSIDs from the --batch list before generation (N >= 1).",
    )
    sample_grp.add_argument(
        "--sample-seed",
        type=int,
        default=None,
        metavar="N",
        help="Integer seed for --sample RNG (default: non-deterministic).",
    )
    sample_grp.add_argument(
        "--sample-stratified",
        action="store_true",
        help="Group --batch RSIDs by code prefix; sample proportionally per group.",
    )

    # v1.8.0 — validation cache (dormant; populated in v1.12.0)
    cache_grp = p.add_argument_group("validation cache (dormant in v1.8.0; populated in v1.12.0)")
    cache_grp.add_argument(
        "--enable-cache",
        action="store_true",
        help="Instantiate the validation cache (no-op until v1.12.0's quality engine).",
    )
    cache_grp.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear cache state at run start.",
    )
    cache_grp.add_argument(
        "--cache-ttl",
        type=_positive_int,
        default=3600,
        metavar="SECONDS",
        help="Cache entry TTL in seconds (default: 3600).",
    )
    cache_grp.add_argument(
        "--cache-size",
        type=_positive_int,
        default=1000,
        metavar="ENTRIES",
        help="Cache LRU max-size (default: 1000).",
    )

    # v1.9.0 — field-level shaping + naming audits  (extended in v1.12.0)
    quality_grp = p.add_argument_group(
        "quality audits + name matching (v1.9.0+, severity engine v1.12.0+)",
    )
    quality_grp.add_argument(
        "--audit-naming",
        action="store_true",
        help="Add naming-pattern audit to the SDR document (case styles, prefix groups, recommendations).",
    )
    quality_grp.add_argument(
        "--flag-stale",
        action="store_true",
        help="Flag components with stale-name patterns (test/old/deprecated, _vN suffix, date suffix) in the SDR document.",
    )
    quality_grp.add_argument(
        "--name-match",
        choices=("exact", "insensitive", "fuzzy"),
        default="insensitive",
        help="Strategy for resolving <RSID_OR_NAME> tokens to canonical RSIDs (default: insensitive).",
    )
    quality_grp.add_argument(
        "--extended-fields",
        action="store_true",
        help="In --diff mode, include extended fields (description, tags, category, etc.) in comparison. Off by default.",
    )

    # v1.12.0 — severity engine
    quality_grp.add_argument(
        "--quality-report",
        choices=("json", "csv"),
        default=None,
        help="Emit a machine-readable quality report alongside the SDR output (v1.12.0).",
    )
    quality_grp.add_argument(
        "--quality-policy",
        type=Path,
        default=None,
        help="Path to a JSON quality-policy file. CLI flags win over policy values (v1.12.0).",
    )
    quality_grp.add_argument(
        "--fail-on-quality",
        choices=("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"),
        default=None,
        help="Exit with code 17 if any issue at or above this severity exists (v1.12.0).",
    )

    notion_group = p.add_argument_group("Notion Integration (v1.18.0+)")
    notion_group.add_argument(
        "--push-to-notion",
        type=str,
        default=None,
        metavar="JSON_FILE",
        dest="push_to_notion",
        help=(
            "Push an existing SDR JSON artifact (or snapshot envelope) to Notion "
            "without re-calling the Adobe Analytics API. Requires NOTION_TOKEN "
            "and NOTION_PARENT_PAGE_ID env vars."
        ),
    )
    notion_group.add_argument(
        "--notion-force-new",
        action="store_true",
        default=False,
        dest="notion_force_new",
        help=(
            "Force creation of a new Notion page even if one already exists for "
            "this RSID. The new page ID replaces the old entry in "
            ".notion_pages.json."
        ),
    )
    notion_group.add_argument(
        "--notion-registry-database",
        type=str,
        default=None,
        metavar="DATABASE_ID",
        dest="notion_registry_database",
        help=(
            "Override NOTION_REGISTRY_DATABASE_ID for this run. When set "
            "(via flag or env var), --format notion / --push-to-notion runs "
            "also upsert a row into the named Notion SDR Registry database. "
            "(v1.19.0)"
        ),
    )
    notion_group.add_argument(
        "--no-notion-registry",
        action="store_true",
        default=False,
        dest="no_notion_registry",
        help=(
            "Skip the registry database upsert for this run even when "
            "NOTION_REGISTRY_DATABASE_ID is set. The detail page is still "
            "written. (v1.19.0)"
        ),
    )
    notion_group.add_argument(
        "--notion-prune-orphans",
        action="store_true",
        default=False,
        dest="notion_prune_orphans",
        help="Archive Notion pages abandoned by --notion-force-new. Preview by default; --yes archives.",
    )
    notion_group.add_argument(
        "--notion-repair-database",
        action="store_true",
        default=False,
        dest="notion_repair_database",
        help="Additively add missing registry-database properties. Preview by default; --yes applies.",
    )
    notion_group.add_argument(
        "--notion-company",
        type=str,
        default=None,
        metavar="NAME",
        dest="notion_company",
        help="Company value for the registry row; makes the row key (Company, RSID). Overrides NOTION_REGISTRY_COMPANY.",
    )
    notion_group.add_argument(
        "--notion-create-database",
        action="store_true",
        default=False,
        dest="notion_create_database",
        help=(
            "Create the Notion SDR Registry database with the full canonical schema "
            "under NOTION_PARENT_PAGE_ID. Preview by default; --yes creates it and "
            "prints the new database id to set as NOTION_REGISTRY_DATABASE_ID."
        ),
    )
    notion_group.add_argument(
        "--notion-database-title",
        type=str,
        default=None,
        metavar="NAME",
        dest="notion_database_title",
        help="Title for the database created by --notion-create-database (default: AA SDR Registry).",
    )

    return p
