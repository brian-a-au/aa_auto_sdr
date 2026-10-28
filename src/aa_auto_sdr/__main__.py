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
        "  aa_auto_sdr --render-from TOKEN      Re-render reports offline from saved SDR JSON or a snapshot (no auth)\n"
        "  aa_auto_sdr --list-reportsuites      List all report suites visible to the org\n"
        "  aa_auto_sdr --list-metrics <RSID>    List metrics (also: --list-dimensions/segments/...)\n"
        "  aa_auto_sdr --describe-reportsuite <RSID>  Print metadata + per-component counts\n"
        "  aa_auto_sdr --profile-add <name>     Create a credentials profile\n"
        "  aa_auto_sdr --profile <name> ...     Use a named profile\n"
        "  aa_auto_sdr --show-config            Show resolved credentials source\n"
        "  aa_auto_sdr --config-status          Print full credential resolution chain\n"
        "  aa_auto_sdr --validate-config        Validate credential shape without calling Adobe\n"
        "  aa_auto_sdr --sample-config          Emit a config.json template to stdout\n"
        "  aa_auto_sdr --stats [<RSID>...]      Quick component counts per RSID\n"
        "  aa_auto_sdr --inventory-summary [<RSID>...]  Cross-RSID aggregate rollup (totals/min/max/avg)\n"
        "  aa_auto_sdr <RSID...> --trending-window <DURATION>  Per-RSID drift window over snapshots (Nh|Nd|Nw)\n"
        "  aa_auto_sdr <RSID...> --compare-with-prev    Diff latest vs previous snapshot per RSID\n"
        "  aa_auto_sdr <RSID...> --watch --interval <DUR>  Foreground monitoring loop emitting NDJSON change events\n"
        "  aa_auto_sdr <RSID> --git-commit               Commit the saved snapshot to git (auto-inits snapshot dir)\n"
        "  aa_auto_sdr <RSID> --git-commit --git-push    Commit and push (requires user's git config for remote/auth)\n"
        "  aa_auto_sdr --interactive            Pick an RSID interactively; emit to stdout\n"
        "  aa_auto_sdr <RSID> --show-timings    Print per-stage timings to stderr at end of run\n"
        "  aa_auto_sdr <RSID> --run-summary-json PATH  Emit a JSON run summary to PATH or '-'\n"
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
        "Batch parallelism:\n"
        "  --workers N               Parallel worker threads for --batch (default: 1, max: 16)\n"
        "  --fail-fast               Stop the batch on the first failure (sequential or parallel)\n"
        "\n"
        "Batch sampling:\n"
        "  --sample N                Subset N RSIDs from the --batch list before generation (N >= 1)\n"
        "  --sample-seed N           Integer seed for --sample RNG (default: non-deterministic)\n"
        "  --sample-stratified       Group --batch RSIDs by code prefix; sample proportionally per group\n"
        "\n"
        "Validation cache:\n"
        "  --enable-cache            Instantiate the validation cache used by the quality engine\n"
        "  --clear-cache             Clear cache state at run start\n"
        "  --cache-ttl SECONDS       Cache entry TTL in seconds (default: 3600)\n"
        "  --cache-size ENTRIES      Cache LRU max-size (default: 1000)\n"
        "\n"
        "Quality audits + name matching:\n"
        "  --audit-naming            Add naming-pattern audit to the SDR document (case styles, prefix groups, recommendations).\n"
        "  --flag-stale              Flag components with stale-name patterns (test/old/deprecated, _vN suffix, date suffix).\n"
        "  --name-match {exact,insensitive,fuzzy}  Strategy for resolving <RSID_OR_NAME> tokens (default: insensitive).\n"
        "  --extended-fields         In --diff mode, include extended fields (description, tags, category, etc.). Off by default.\n"
        "  --quality-report {json,csv}      Emit a machine-readable quality report alongside the SDR output.\n"
        "  --quality-policy <PATH>          JSON quality-policy file; CLI flags win over policy values.\n"
        "  --fail-on-quality {CRITICAL,HIGH,MEDIUM,LOW,INFO}  Exit with code 17 if any issue at or above this severity exists.\n"
        "\n"
        "Watch mode:\n"
        "  --watch                   Loop over RSID(s) at --interval; emit NDJSON change events to stdout\n"
        "  --interval DURATION       Watch cadence (Nh|Nd|Nw, e.g. '1h'). Required with --watch.\n"
        "  --watch-threshold N       Min component change count to emit a change event (0=heartbeat, default 1);\n"
        "                            a report-suite setting change always emits\n"
        "\n"
        "Git integration:\n"
        "  --git-commit              After saving a snapshot, commit it to the snapshot dir's git repo (auto-inits on first use)\n"
        "  --git-push                Push after a successful --git-commit (requires --git-commit)\n"
        "  --git-message TEXT        Override the auto-generated commit message (requires --git-commit)\n"
        "\n"
        "Template-fill mode:\n"
        "  --template PATH           Path to an existing .xlsx template; switches Excel writer to fill mode\n"
        "  --template-organization NAME  Organization name written to Glossary!C2 (requires --template)\n"
        "\n"
        "Output:\n"
        "  --format FMT              Generate: excel|csv|json|html|markdown|all|reports|data|ci; list/inspect: json|csv\n"
        "  --output-dir DIR          Directory for generated SDR files (default: current directory)\n"
        "  --output PATH             Output path for list/inspect commands; '-' writes to stdout\n"
        "  --metrics-only            Generate an SDR with only metrics\n"
        "  --dimensions-only         Generate an SDR with only dimensions\n"
        "  --dry-run                 Preview output paths (or --prune-snapshots deletions) without writing\n"
        "  --open                    Open the generated output in the OS default app after writing\n"
        "  --agent-mode              Preset: --format json --output - --log-format json for options not passed\n"
        "\n"
        "Inspection:\n"
        "  --list-virtual-reportsuites  List all virtual report suites\n"
        "  --list-segments RSID      List segments for one report suite\n"
        "  --list-calculated-metrics RSID  List calculated metrics for one report suite\n"
        "  --list-classification-datasets RSID  List classification datasets for one report suite\n"
        "  --filter STR              Case-insensitive substring match on name (list/inspect only)\n"
        "  --exclude STR             Case-insensitive substring exclusion on name (list/inspect only)\n"
        "  --sort FIELD              Sort field (list/inspect only; allowed fields vary by command)\n"
        "  --limit N                 Cap output to N records (list/inspect only)\n"
        "\n"
        "Profiles:\n"
        "  --profile-list            List credentials profiles in ~/.aa/orgs/\n"
        "  --profile-test NAME       Authenticate a profile and print PASS/FAIL\n"
        "  --profile-show NAME       Show a profile with the client ID masked (no secret)\n"
        "  --profile-import NAME FILE  Import a JSON file as a credentials profile\n"
        "  --profile-overwrite       Let --profile-import replace an existing profile\n"
        "\n"
        "Snapshots:\n"
        "  --snapshot-dir PATH       Override the active profile's snapshot directory\n"
        "  --auto-snapshot           Save a snapshot per RSID on generate/batch (requires --profile)\n"
        "  --list-snapshots          List snapshots in the active snapshot dir (pass <RSID> to filter)\n"
        "  --prune-snapshots         Delete snapshots by retention policy (needs --keep-last or --keep-since)\n"
        "  --keep-last N             Retention: keep the N most recent snapshots per RSID\n"
        "  --keep-since DURATION     Retention: keep snapshots newer than DURATION (e.g. 30d, 12h, 4w)\n"
        "  --auto-prune              Apply the retention policy after --auto-snapshot or with --prune-snapshots\n"
        "  -y, --yes                 Skip confirmation prompts\n"
        "\n"
        "Diff output:\n"
        "  --summary                 Count-only summary, no per-field detail\n"
        "  --side-by-side            Show modified fields side by side (console/markdown only)\n"
        "  --changes-only            Drop component types with no changes\n"
        "  --quiet-diff              Suppress unchanged trailers; show only changed sections\n"
        "  --show-only TYPES         Restrict output to listed component types (CSV)\n"
        "  --ignore-fields CSV       Field names to skip during compare (e.g. description,tags)\n"
        "  --max-issues N            Cap added/removed/modified items per component type\n"
        "  --diff-labels A=X B=Y     Override the Source/Target labels\n"
        "  --reverse-diff            Swap a and b before compare\n"
        "  --warn-threshold N        Exit with code 3 if total changes >= N\n"
        "  --color-theme {default,accessible}  Diff colors; 'accessible' uses blue/orange\n"
        "\n"
        "Logging:\n"
        "  --log-level LEVEL         DEBUG|INFO|WARNING|ERROR|CRITICAL (default: INFO, or LOG_LEVEL)\n"
        "  --log-format {text,json}  Log format; 'json' writes NDJSON\n"
        "  -q, --quiet               Suppress progress and INFO console output; errors and final paths still print\n"
        "\n"
        "Notion (optional extra):\n"
        "  --push-to-notion JSON_FILE  Push an existing SDR JSON or snapshot to Notion without calling Adobe\n"
        "  --notion-force-new        Create a new Notion page even if one exists for this RSID\n"
        "  --notion-registry-database ID  Override NOTION_REGISTRY_DATABASE_ID for this run\n"
        "  --no-notion-registry      Skip the registry database row for this run\n"
        "  --notion-company NAME     Company value for the registry row\n"
        "  --notion-prune-orphans    Archive pages left by --notion-force-new (preview; --yes applies)\n"
        "  --notion-repair-database  Add missing registry database properties (preview; --yes applies)\n"
        "  --notion-create-database  Create the SDR Registry database (preview; --yes creates)\n"
        "  --notion-database-title NAME  Title for --notion-create-database (default: AA SDR Registry)\n"
        "\n"
        "See CHANGELOG.md for release history.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in _FASTPATH_VERSION:
        return _print_version()
    if args and args[0] in _FASTPATH_HELP:
        return _print_help()
    # Diagnostic fast paths only short-circuit for their exact standalone form.
    # When extra tokens follow (e.g. `--exit-codes --git-commit`), fall through
    # to run(), where the parser + modifier validators reject the combination —
    # so validation does not depend on whether the diagnostic flag came first.
    if args and args[0] == "--exit-codes" and len(args) == 1:
        from aa_auto_sdr.cli.commands.exit_codes import run_list_exit_codes

        return run_list_exit_codes()
    if args and args[0] == "--explain-exit-code" and len(args) <= 2:
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
    if args and args[0] == "--completion" and len(args) <= 2:
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
