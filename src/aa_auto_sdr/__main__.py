"""Fast-path entry point. Handles --version/--help/--exit-codes/--completion
without importing any heavy dependency. Delegates everything else to cli.main."""

from __future__ import annotations

import sys

from aa_auto_sdr.core.version import __version__

_FASTPATH_VERSION = {"-V", "--version"}
_FASTPATH_HELP = {"-h", "--help"}


def _print_version() -> int:
    print(f"aa_auto_sdr {__version__}")
    return 0


def _print_help() -> int:
    print(
        "aa_auto_sdr — Adobe Analytics SDR Generator (API 2.0 only)\n"
        "\n"
        "Usage:\n"
        "  aa_auto_sdr <RSID-or-name>           Generate SDR for one report suite\n"
        "  aa_auto_sdr <RSID...> [<NAME>...]    Auto-batch when 2+ identifiers given (RSIDs/names may mix)\n"
        "  aa_auto_sdr --batch <RSID...>        Same as above; explicit form still supported\n"
        "  aa_auto_sdr --diff <a> <b>           Compare two snapshots (path|@ts|@latest|@previous|git:ref:path)\n"
        "  aa_auto_sdr <RSID> --snapshot --profile P  Generate + persist snapshot under ~/.aa/orgs/P/snapshots/\n"
        "  aa_auto_sdr --list-reportsuites      List all report suites visible to the org\n"
        "  aa_auto_sdr --list-metrics <RSID>    List metrics (also: --list-dimensions/segments/...)\n"
        "  aa_auto_sdr --describe-reportsuite <RSID>  Print metadata + per-component counts\n"
        "  aa_auto_sdr --profile-add <name>     Create a credentials profile\n"
        "  aa_auto_sdr --profile <name> ...     Use a named profile\n"
        "  aa_auto_sdr --show-config            Show resolved credentials source\n"
        "  aa_auto_sdr --config-status          Print full credential resolution chain (v1.2)\n"
        "  aa_auto_sdr --validate-config        Validate credential shape without calling Adobe (v1.2)\n"
        "  aa_auto_sdr --sample-config          Emit a config.json template to stdout (v1.2)\n"
        "  aa_auto_sdr --stats [<RSID>...]      Quick component counts per RSID (v1.2)\n"
        "  aa_auto_sdr --inventory-summary [<RSID>...]  Cross-RSID aggregate rollup (totals/min/max/avg) (v1.11.0)\n"
        "  aa_auto_sdr <RSID...> --trending-window <DURATION>  Per-RSID drift window over snapshots (Nh|Nd|Nw) (v1.13.0)\n"
        "  aa_auto_sdr <RSID...> --compare-with-prev    Diff latest vs previous snapshot per RSID (v1.13.0)\n"
        "  aa_auto_sdr <RSID...> --watch --interval <DUR>  Foreground monitoring loop emitting NDJSON change events (v1.14.0)\n"
        "  aa_auto_sdr <RSID> --git-commit               Commit the saved snapshot to git (auto-inits snapshot dir) (v1.15.0)\n"
        "  aa_auto_sdr <RSID> --git-commit --git-push    Commit and push (requires user's git config for remote/auth) (v1.15.0)\n"
        "  aa_auto_sdr --interactive            Pick an RSID interactively; emit to stdout (v1.2)\n"
        "  aa_auto_sdr <RSID> --show-timings    Print per-stage timings to stderr at end of run (v1.2.1)\n"
        "  aa_auto_sdr <RSID> --run-summary-json PATH  Emit a JSON run summary to PATH or '-' (v1.2.1)\n"
        "  aa_auto_sdr --exit-codes             List every exit code with one-line meaning\n"
        "  aa_auto_sdr --explain-exit-code <N>  Detailed explanation for one exit code\n"
        "  aa_auto_sdr --completion <SHELL>     Emit a shell completion script (bash|zsh|fish)\n"
        "  aa_auto_sdr -V | --version           Print version\n"
        "  aa_auto_sdr -h | --help              Print this help\n"
        "\n"
        "Retry tuning:\n"
        "  --max-retries N           Max retries on transient API failures (default: 3)\n"
        "  --retry-base-delay SECS   Base delay for exponential backoff (default: 0.5)\n"
        "  --retry-max-delay SECS    Maximum delay between retries (default: 10.0)\n"
        "\n"
        "Batch parallelism (v1.8.0+):\n"
        "  --workers N               Parallel worker threads for --batch (default: 1, max: 16)\n"
        "  --fail-fast               Cancel pending workers on first batch failure\n"
        "\n"
        "Batch sampling (v1.10.0+):\n"
        "  --sample N                Subset N RSIDs from the --batch list before generation (N >= 1)\n"
        "  --sample-seed N           Integer seed for --sample RNG (default: non-deterministic)\n"
        "  --sample-stratified       Group --batch RSIDs by code prefix; sample proportionally per group\n"
        "\n"
        "Validation cache (dormant in v1.8.0; populated in v1.12.0):\n"
        "  --enable-cache            Instantiate the validation cache (no-op until v1.12.0)\n"
        "  --clear-cache             Clear cache state at run start\n"
        "  --cache-ttl SECONDS       Cache entry TTL in seconds (default: 3600)\n"
        "  --cache-size ENTRIES      Cache LRU max-size (default: 1000)\n"
        "\n"
        "Quality audits + name matching (v1.9.0+, severity engine v1.12.0+):\n"
        "  --audit-naming            Add naming-pattern audit to the SDR document (case styles, prefix groups, recommendations).\n"
        "  --flag-stale              Flag components with stale-name patterns (test/old/deprecated, _vN suffix, date suffix).\n"
        "  --name-match {exact,insensitive,fuzzy}  Strategy for resolving <RSID_OR_NAME> tokens (default: insensitive).\n"
        "  --extended-fields         In --diff mode, include extended fields (description, tags, category, etc.). Off by default.\n"
        "  --quality-report {json,csv}      Emit a machine-readable quality report alongside the SDR output (v1.12.0).\n"
        "  --quality-policy <PATH>          JSON quality-policy file; CLI flags win over policy values (v1.12.0).\n"
        "  --fail-on-quality {CRITICAL,HIGH,MEDIUM,LOW,INFO}  Exit with code 17 if any issue at or above this severity exists (v1.12.0).\n"
        "\n"
        "Watch mode (v1.14.0):\n"
        "  --watch                   Loop over RSID(s) at --interval; emit NDJSON change events to stdout\n"
        "  --interval DURATION       Watch cadence (Nh|Nd|Nw, e.g. '1h'). Required with --watch.\n"
        "  --watch-threshold N       Min total change count to emit a change event (0=heartbeat, default 1)\n"
        "\n"
        "Git integration (v1.15.0):\n"
        "  --git-commit              After saving a snapshot, commit it to the snapshot dir's git repo (auto-inits on first use)\n"
        "  --git-push                Push after a successful --git-commit (requires --git-commit)\n"
        "  --git-message TEXT        Override the auto-generated commit message (requires --git-commit)\n"
        "\n"
        "Template-fill mode (v1.16.0):\n"
        "  --template PATH           Path to an existing .xlsx template; switches Excel writer to fill mode\n"
        "  --template-organization NAME  Organization name written to Glossary!C2 (requires --template)\n"
        "\n"
        "v1.2.0: diff polish (quiet, labels, reverse, warn-threshold, filters); --stats / --interactive; --dry-run for generate/batch; generation modifiers (--metrics-only, --dimensions-only); --profile-overwrite; config introspection (--config-status, --validate-config, --sample-config); --open and --yes.\n"
        "v1.2.1: --show-timings + --run-summary-json wired (M-7); typed wrappers in api/fetch.py + CI-enforced no-SDK-reach-through meta-test (M-1); breaking change: --prune-snapshots non-interactive stdin without --yes now exits 2 (USAGE) instead of 0 (M-6).\n"
        "v1.8.0: parallel --batch workers (--workers, --fail-fast); validation cache scaffold (--enable-cache, --clear-cache, --cache-ttl, --cache-size).\n"
        "v1.9.0: field-level shaping + naming audits (--audit-naming, --flag-stale, --name-match, --extended-fields).\n"
        "v1.10.0: --batch RSID sampling (--sample, --sample-seed, --sample-stratified).\n"
        "v1.11.0: --inventory-summary cross-RSID rollup (table|json|csv).\n"
        "v1.12.0: quality severity engine (--quality-report, --quality-policy, --fail-on-quality); ValidationCache activated.\n"
        "v1.12.1: rsid added to quality_audit_complete + quality_gate_evaluated logs; vocabulary validator polish.\n"
        "v1.13.0: drift / trending windows (--trending-window, --compare-with-prev); cja's include-drift roadmap row dropped.\n"
        "v1.14.0: watch / scheduled mode (--watch, --interval, --watch-threshold); on-change hook dropped per CHANGELOG.\n"
        "v1.15.0: git integration (--git-commit, --git-push, --git-message). See CHANGELOG for dropped flags.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in _FASTPATH_VERSION:
        return _print_version()
    if args and args[0] in _FASTPATH_HELP:
        return _print_help()
    if args and args[0] == "--exit-codes":
        from aa_auto_sdr.cli.commands.exit_codes import run_list_exit_codes

        return run_list_exit_codes()
    if args and args[0] == "--explain-exit-code":
        from aa_auto_sdr.cli.commands.exit_codes import run_explain_exit_code

        if len(args) < 2:
            print("error: --explain-exit-code requires a CODE argument", file=sys.stderr, flush=True)
            return 2
        try:
            code = int(args[1])
        except ValueError:
            print(f"error: '{args[1]}' is not a valid exit code (must be int)", file=sys.stderr, flush=True)
            return 2
        return run_explain_exit_code(code)
    if args and args[0] == "--completion":
        from aa_auto_sdr.cli.commands.completion import run_completion

        if len(args) < 2:
            print("error: --completion requires a SHELL argument (bash, zsh, or fish)", file=sys.stderr, flush=True)
            return 2
        return run_completion(args[1])
    if args and args[0] == "--notion-print-database-schema":
        # Print-and-exit: must be used alone. Combining it with generation
        # work (RSIDs, --batch, etc.) is operator confusion → USAGE.
        if len(args) > 1:
            print(
                "error: --notion-print-database-schema cannot be combined with other arguments",
                file=sys.stderr,
                flush=True,
            )
            return 2
        from aa_auto_sdr.cli.commands.notion_schema import run_notion_print_schema

        return run_notion_print_schema()
    from aa_auto_sdr.cli.main import run

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
