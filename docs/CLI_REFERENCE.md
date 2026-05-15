# CLI Reference

Every flag and what it does. For onboarding, see [`QUICKSTART.md`](QUICKSTART.md). For the agent-mode contract see [`AGENTS.md`](../AGENTS.md). The full source of truth for exit codes is `src/aa_auto_sdr/core/exit_codes.py` (consumed by `aa_auto_sdr --exit-codes`).

## Quick navigation

- [Common options](#common-options) — global flags
- [Exit codes](#exit-codes) — table + lookup commands
- [Generation](#generation) — single, auto-batch, `--batch`, modifiers
- [Discovery and inspection](#discovery-and-inspection) — list / describe / stats / interactive
- [Snapshot](#snapshot) — capture, auto-snapshot, prune, list
- [Diff](#diff) — snapshot comparison, modifiers, polish
- [Trending and drift](#trending-and-drift)
- [Watch and scheduled](#watch-and-scheduled)
- [Quality severity engine](#quality-severity-engine)
- [Inventory and stats](#inventory-and-stats)
- [Batch tuning](#batch-tuning) — workers, sampling
- [Validation cache](#validation-cache)
- [Resilience](#resilience) — retries
- [Profile and config](#profile-and-config)
- [Logging and observability](#logging-and-observability)
- [Machine-readable errors](#machine-readable-errors)
- [Fast-path actions](#fast-path-actions)

## Common options

| Flag | Applies to | Behavior |
|----|----|----|
| `--format FMT` | generate, list/inspect, diff | Per-action allowlist (excel/csv/json/html/markdown plus aliases all/reports/data/ci for generate; json/csv for list/inspect; console/json/markdown/pr-comment for diff). |
| `--output PATH \| -` | list/inspect, diff, generate JSON pipe | File path, or `-` for stdout pipe (where supported). |
| `--output-dir DIR` | generate, batch | Output directory for SDR file(s). Default: cwd. |
| `--filter STR` | list/inspect | Case-insensitive substring on `name`. |
| `--exclude STR` | list/inspect | Case-insensitive substring exclusion on `name`. |
| `--sort FIELD` | list/inspect | Sort by allowlisted field per command. |
| `--limit N` | list/inspect | Cap output to N records. |
| `--profile NAME` | all (when needed) | Use named profile for credentials. Required for `<rsid>@<spec>` diff tokens and `--snapshot`. |
| `--yes` / `-y` | destructive actions | Skip confirmation prompts. Non-tty stdin refuses to prompt and aborts safely without `--yes`. |

## Exit codes

Source of truth: `src/aa_auto_sdr/core/exit_codes.py`. Run `aa_auto_sdr --exit-codes` for the one-line table or `aa_auto_sdr --explain-exit-code CODE` for full remediation.

| Code | Meaning |
|----|----|
| 0 | Success |
| 1 | Generic error |
| 2 | Argument / usage error (argparse) |
| 3 | Diff `--warn-threshold` exceeded (diff itself ran successfully) |
| 10 | Bad config or missing credentials |
| 11 | Adobe OAuth Server-to-Server failure |
| 12 | Adobe Analytics API request failed |
| 13 | Report suite or other resource not found |
| 14 | `--batch` partial success — some ok, some failed |
| 15 | Output writer failure |
| 16 | Snapshot resolve / schema / git failure |
| 17 | Quality gate breached: `--fail-on-quality` threshold exceeded |

## Generation

### `aa_auto_sdr <RSID-or-name>`

Generate one SDR for a report suite. Positional argument accepts an RSID exact-match or a report-suite name (case-insensitive exact match). When a name matches multiple suites, an SDR is produced for each.

```bash
uv run aa_auto_sdr dgeo1xxpnwcidadobestore
uv run aa_auto_sdr "Adobe Store" --format json --output-dir /tmp/sdr
```

Default format: Excel. Output filename keys off the canonical RSID.

Exit codes: `0`, `10`, `11`, `12`, `13`, `15`, `17` (when `--fail-on-quality` is set).

### `aa_auto_sdr <RSID...> [<NAME>...]` — auto-batch

Pass two or more identifiers and the tool automatically routes to batch mode — no `--batch` flag needed. **RSIDs and names may be mixed freely** in a single invocation; per-RSID name resolution happens inside the batch loop.

```bash
uv run aa_auto_sdr rs1 rs2 rs3 --output-dir /tmp/sdr
uv run aa_auto_sdr dgeo1xxpnwcidadobestore "Adobe Store" demo.prod --format json
uv run aa_auto_sdr rs1 "Adobe Store" --profile prod --auto-snapshot --auto-prune --keep-last 5
```

`--output -` is rejected when more than one identifier is given (multi-SDR cannot share one stream → exit 15). Same continue-on-error semantics, summary banner, and partial-success exit code as explicit `--batch`.

### `aa_auto_sdr --batch RSID1 RSID2 ...`

Explicit batch form. Equivalent to auto-batch above. Sequential by default; with `--workers N` (see [Batch tuning](#batch-tuning)) workers run in parallel. Continue-on-error: a per-RSID failure does not stop the rest. After the run, a CJA-style summary banner prints counts, success rate, total bytes/duration, and per-RSID ✓/✗ rows.

```bash
uv run aa_auto_sdr --batch RS1 RS2 RS3 --format json --output-dir /tmp/sdr
```

Mutually exclusive with positional RSIDs. `--output -` is rejected.

Exit codes: `0`, `14` (partial), `17` (quality gate, if `--fail-on-quality` is set), or the last failure's exit code if all failed.

### Generation modifiers

| Flag | Behavior |
|---|---|
| `--metrics-only` / `--dimensions-only` (mutex) | Slim the SDR by skipping API calls for excluded component types. Cannot be combined with `--snapshot` / `--auto-snapshot` (filtered snapshots produce misleading diffs → exit 2). |
| `--dry-run` | Resolve credentials, authenticate, resolve RSID/name → canonical RSIDs, then print what would be written without doing the heavy component fetch or any file writes. |
| `--open` | After successful generation, open the first output file (single) or output dir (batch) in the OS default app. Best-effort; silently skips on headless. |

```bash
aa_auto_sdr <RSID> --metrics-only --format json --output-dir /tmp/metrics-only
aa_auto_sdr <RSID> --dry-run --auto-snapshot --profile prod
```

### `--template PATH` *(v1.16.0)*

> **Workflow guide:** [`docs/TEMPLATE_WORKFLOW.md`](TEMPLATE_WORKFLOW.md) — first-run + batch + troubleshooting walkthroughs, coverage map, log-signals reference.

Path to an existing `.xlsx` template. When set, every resolved `excel` format slot is swapped to `excel-template` (the template-fill writer). Adobe's official `aa_en_BRD_SDR_template.xlsx` is the canonical target; any `.xlsx` with the same anchor layout (sheet names, `B4` section titles, `ID` header markers in rows 5–10) also works.

The fill writer is non-destructive: it matches existing skeleton rows by id and overwrites in-place, leaves non-matching skeleton rows untouched, and appends API-only ids past `max_row` (with a `template_overflow` WARNING).

USAGE (2) if the path is missing, a directory, or non-`.xlsx`. USAGE (2) if combined with `--diff` / `--watch` / a `--list-*` action / `--trending-window` / `--compare-with-prev` / `--inventory-summary` / `--describe-reportsuite`. USAGE (2) if `--format` resolves to a set without `excel` / `excel-template`.

### `--template-organization NAME` *(v1.16.0)*

Organization string written to `Glossary!C2` — the source-of-truth cell every other sheet's `C2` formula reads. Defaults to the report suite name. Requires `--template`.

## Discovery and inspection

### `aa_auto_sdr --list-reportsuites` / `--list-virtual-reportsuites`

List every (virtual) report suite visible to the org's credentials. Both accept `--filter STR`, `--exclude STR`, `--sort FIELD`, `--limit N`, `--format json|csv` (default: fixed-width table to stdout), `--output PATH|-`.

### `aa_auto_sdr --describe-reportsuite <RSID-or-name>`

Print metadata + per-component counts (no full SDR built).

### `aa_auto_sdr --list-{metrics,dimensions,segments,calculated-metrics,classification-datasets} <RSID>`

Lists one component type for one RS. Same options as discovery.

```bash
uv run aa_auto_sdr --list-metrics demo.prod --filter page --sort name --limit 10
```

### `aa_auto_sdr --stats [<RSID>...]`

Quick component counts per RSID — no full SDR build, no metadata. Lighter than `--describe-reportsuite`. With no positional args, lists every visible report suite.

- `--format table` (default): `RSID  NAME  DIM  MET  SEG  CALC  VRS  CLS`
- `--format json`: `[{"rsid", "name", "counts": {...}}, ...]`

### `aa_auto_sdr --interactive`

Print a numbered menu of visible report suites to stderr, prompt for selection by index or `all` on stdin, emit the chosen RSID(s) to stdout. Designed for shell composition:

```bash
RSIDS=$(aa_auto_sdr --interactive --profile prod) && aa_auto_sdr $RSIDS --auto-snapshot
```

Exit 130 on Ctrl-C. Exit 2 (USAGE) on out-of-range index.

## Snapshot

For deeper coverage of snapshot semantics, file format, retention, and the diff resolver see [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md).

### `<RSID> --snapshot --profile <name>`

Persist the built SDR to `~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-timestamp>.json` alongside the format outputs. Requires `--profile`. Works on `<RSID>` and `--batch`.

`--snapshot --output -` works — the snapshot is an out-of-band side effect.

### `<RSID> --auto-snapshot --profile <name>`

Like `--snapshot` but designed to be set as a default for every run. Combines with `--snapshot` to a single save (no double-write). Requires `--profile`.

### `<RSID> --auto-prune --keep-last N | --keep-since DURATION`

After auto-saving, apply a retention policy and delete older snapshots per RSID. Requires `--profile` and exactly one of `--keep-last` or `--keep-since`. Silent no-op if `--auto-snapshot` (or `--snapshot`) isn't also set.

- `--keep-last N` — keep the N most recent snapshots **per RSID**.
- `--keep-since DURATION` — keep snapshots newer than DURATION (`Nh|Nd|Nw`). Bad format → exit 10.

```bash
uv run aa_auto_sdr <RSID> --profile prod --auto-snapshot --auto-prune --keep-last 5
uv run aa_auto_sdr --batch RS1 RS2 --profile prod --auto-snapshot --auto-prune --keep-since 30d
```

### `aa_auto_sdr --list-snapshots [<RSID>] (--profile <name> | --snapshot-dir <path>)`

List snapshots in the active snapshot dir (`--snapshot-dir` if set, otherwise the profile's snapshot dir). Optional positional `<RSID>` narrows to one suite.

- `--format table` (default): fixed-width columns `RSID`, `CAPTURED_AT`, `PATH`.
- `--format json`: `[{"rsid", "captured_at", "path"}, ...]`. `captured_at` is canonical ISO-8601 (with colons).

### `aa_auto_sdr --prune-snapshots [<RSID>] --keep-last N | --keep-since DURATION (--profile <name> | --snapshot-dir <path>)`

Apply the retention policy and delete snapshots that fail the keep test. Per-RSID. `--dry-run` previews deletions without unlinking.

```bash
uv run aa_auto_sdr --prune-snapshots --profile prod --keep-last 10 --dry-run
uv run aa_auto_sdr --prune-snapshots RS1 --profile prod --keep-since 90d
```

On non-interactive stdin without `--yes` the command refuses with exit code 2.

## Diff

### `aa_auto_sdr --diff <a> <b>`

Compute a structured diff between two snapshot envelopes. Each token is one of:

| Token form | Example | Resolution |
|----|----|----|
| File path | `./snap-a.json` | Read JSON, validate schema, compare. |
| `<rsid>@<timestamp>` | `demo.prod@2026-04-26T17-29-01+00-00` | Look in the active snapshot dir under `<rsid>/`. |
| `<rsid>@latest` | `demo.prod@latest` | Most-recent file in that dir. |
| `<rsid>@previous` | `demo.prod@previous` | Second-most-recent file. |
| `git:<ref>:<path>` | `git:HEAD~1:snapshots/x.json` | `git show <ref>:<path>` from cwd. |

Profile-form tokens (`<rsid>@<spec>`) require `--profile` or `--snapshot-dir`. The active snapshot dir is `--snapshot-dir` if set, otherwise `~/.aa/orgs/<profile>/snapshots/`.

`--format console|json|markdown|pr-comment` (default `console`). `--output -` for json/markdown/pr-comment pipes; rejected for console (use `--format json|markdown` for pipes).

```bash
uv run aa_auto_sdr --diff demo.prod@latest demo.prod@previous --profile prod
uv run aa_auto_sdr --diff a.json b.json --format json --output -
uv run aa_auto_sdr --diff git:HEAD~1:snap.json git:HEAD:snap.json
```

Exit codes: `0`, `3` (`--warn-threshold` exceeded), `15` (bad format/output combo), `16` (snapshot resolve / schema / git failure).

### Diff modifiers

| Flag | Behavior |
|---|---|
| `--side-by-side` | Render modified-component fields with before/after columns (console). Markdown's existing layout already includes Before/After columns. |
| `--summary` | Collapse output to per-component-type counts; suppress per-item / per-field detail. |
| `--ignore-fields description,tags` | Comma-separated field names to skip during compare. Match is exact at every nesting level. Filtering happens in the comparator, so the resulting `DiffReport` is clean for piped JSON consumers. |
| `--extended-fields` | Include extended fields (description, tags, category, etc.) in comparison. Off by default. |
| `--quiet-diff` | Suppress unchanged trailers; show only changed sections. |
| `--diff-labels A=… B=…` | Override "Source" / "Target" labels in renderer output. |
| `--reverse-diff` | Swap a and b before compare. |
| `--warn-threshold N` | Exit 3 (`WARN`) if total changes ≥ N. Diff itself still runs. |
| `--changes-only` | In rendered output, drop component types with no changes. |
| `--show-only TYPES` | Restrict diff output to listed types (CSV: `metrics,dimensions`). |
| `--max-issues N` | Cap each component's added/removed/modified to N items in render. |
| `--color-theme {default,accessible}` | Diff color palette. |

```bash
aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --summary
aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --format pr-comment | pbcopy
aa_auto_sdr --diff a.json b.json --ignore-fields description,tags --warn-threshold 10
aa_auto_sdr --diff a.json b.json --show-only metrics --max-issues 20
```

**`$GITHUB_STEP_SUMMARY`:** when the env var is set (GitHub Actions does this automatically per job), every `--diff` invocation also appends a markdown render to that file. No flag needed; uses the full unfiltered report.

## Trending and drift

For deeper coverage see [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md).

| Flag | Behavior |
|----|----|
| `--trending-window DURATION` | Rollup across snapshots in a profile-scoped window (`Nh\|Nd\|Nw`). Reads existing snapshots; no API contact. |
| `--compare-with-prev` | Sugar for `--diff <RSID>@previous <RSID>@latest`, scoped by `--profile` or `--snapshot-dir`. |
| `--snapshot-dir PATH` | Override the active profile's snapshot directory. Honored by `--snapshot`, `--diff`, `--list-snapshots`, `--prune-snapshots`, `--compare-with-prev`, `--trending-window`, `--watch`. |

```bash
aa_auto_sdr <RSID> --trending-window 30d --profile prod
aa_auto_sdr rs1 rs2 rs3 --trending-window 30d --format json --profile prod
aa_auto_sdr <RSID> --compare-with-prev --profile prod
```

## Watch and scheduled

```bash
aa_auto_sdr <RSID> --watch --interval 1h --profile prod
```

| Flag | Behavior |
|----|----|
| `--watch` | Foreground monitoring loop. Each cycle: fetch, snapshot, diff, emit one NDJSON event on stdout (`aa-watch-event/v1`). Event types: `baseline` / `change` / `error`. SIGINT/SIGTERM exit 0. |
| `--interval Nh\|Nd\|Nw` | Required with `--watch`. |
| `--watch-threshold N` | Minimum total change count to emit a `change` event (default `1`; `0` emits every cycle = heartbeat). |

Rejected with `--watch`: `--format`, `--quality-policy`, `--fail-on-quality` (exit 2). `--interval` or non-default `--watch-threshold` without `--watch` are also rejected.

## Quality severity engine

Naming audits are severity-tagged and machine-readable. Three flags promote them into a CI gate.

| Flag | Behavior |
|----|----|
| `--audit-naming` | Adds a naming-pattern audit block (case-style counts, prefix groupings, recommendations) to the SDR document. |
| `--flag-stale` | Adds a stale-component block listing components matching stale-keyword / version-suffix / date-pattern regexes. |
| `--name-match {exact,insensitive,fuzzy}` | Name-resolution strategy (default `insensitive`). |
| `--quality-report {json,csv}` | Emit a machine-readable quality report alongside the SDR. Default filename `quality_report_<RSID>_<timestamp>.{json,csv}`. |
| `--quality-policy PATH` | Load a JSON policy file. Top-level keys: `fail_on_quality`, `quality_report`. CLI flags always win over policy values. Hyphen/underscore canonicalization; optional `quality_policy` / `quality` envelope nesting. |
| `--fail-on-quality {CRITICAL,HIGH,MEDIUM,LOW,INFO}` | Exit `17` (`QUALITY`) if any issue at or above the threshold exists. The SDR and snapshot still emit normally. |

`--quality-report` or `--fail-on-quality` without `--audit-naming` / `--flag-stale` auto-enables both audits. Quality flags outside SDR generation (`--stats`, the list-actions, `--inventory-summary`, `--diff`) exit `USAGE` (2). In batch, `PARTIAL_SUCCESS` (14) outranks `QUALITY` (17).

The policy-file key `max_issues` is NOT supported (rejected by the loader with `ConfigError`); the unrelated CLI flag `--max-issues` for `--diff` rendering still exists.

## Inventory and stats

| Flag | Behavior |
|----|----|
| `--stats [<RSID>...]` | Quick component counts per RSID. With no positional args, lists every visible report suite. See [Discovery and inspection](#discovery-and-inspection) for full description. |
| `--inventory-summary` | Cross-RSID aggregate rollup of component counts (totals, min, max, avg per component type) plus a per-RSID detail block. Mutex with other actions. Format allowlist: `table`, `json`, `csv`. |

```bash
aa_auto_sdr --inventory-summary
aa_auto_sdr rs1 rs2 rs3 --inventory-summary --format csv
aa_auto_sdr --inventory-summary --format json
```

## Batch tuning

| Flag | Behavior |
|----|----|
| `--workers N` | Parallel batch workers (1..16, default `1`). Implemented via `ThreadPoolExecutor`. JSON log records on parallel runs include `worker_id`. |
| `--fail-fast` | In parallel batch, cancel pending workers on the first failure (opt-out of continue-on-error default). |
| `--sample N` | Subset N RSIDs from `--batch` before dispatch. `N >= len(batch)` is a no-op. Requires `--batch`. |
| `--sample-seed N` | RNG seed for `--sample` (integer; default non-deterministic). |
| `--sample-stratified` | Group RSIDs by code prefix (split on first `.` / `_` / `-`) and sample proportionally per group. |

When sampling actually applies, the summary banner prints `Sampled X of Y RSIDs (strategy=random[, seed=N])` and the run emits a `batch_sampled` INFO log record.

## Validation cache

| Flag | Behavior |
|----|----|
| `--enable-cache` | Instantiate the validation cache (used by the quality severity engine). |
| `--clear-cache` | Clear cache state at run start. |
| `--cache-ttl SECS` | Cache entry TTL (default `3600`). |
| `--cache-size N` | LRU max entries (default `1000`). |

DEBUG log records emit `cache_event=hit|miss|evict|expire`. Cache keys include the severity-table version so mapping changes invalidate.

## Resilience

For per-RSID API stability under flaky orgs or noisy CI:

| Flag | Behavior |
|----|----|
| `--max-retries N` | Retry attempts on transient SDK failures (429 / 5xx, connection timeout). Default `3`. |
| `--retry-base-delay SECS` | Initial exponential-backoff delay (default `0.5`). |
| `--retry-max-delay SECS` | Cap between retries (default `10.0`). |

Retries fire only on transient failures; permanent errors (auth, validation, unknown RSID) surface immediately. See [`AGENTS.md`](../AGENTS.md) "Retry Budget" for the worst-case request-count math.

## Profile and config

### Profile management

| Command | Purpose |
|---|---|
| `aa_auto_sdr --profile-add <name>` | Interactive prompt; writes `~/.aa/orgs/<name>/config.json`. |
| `aa_auto_sdr --profile <name> …` | Use a named profile for credentials. |
| `aa_auto_sdr --profile-list` | List profile names in `~/.aa/orgs/`. `--format json` for scripts. |
| `aa_auto_sdr --profile-show <NAME>` | Print profile fields with `client_id` masked and `secret` never shown. Includes snapshot count for the profile. Exit 10 if not found. |
| `aa_auto_sdr --profile-test <NAME>` | Live OAuth + `getCompanyId()`. PASS/FAIL. Exit 0 on PASS, 10 on config error, 11 on auth failure. |
| `aa_auto_sdr --profile-import <NAME> <FILE>` | Import a JSON config as a profile. Exit 10 on missing file, bad JSON, missing required fields, or if profile already exists (use `--profile-overwrite`). |
| `aa_auto_sdr --profile-overwrite` | Allow `--profile-import` to overwrite an existing profile. |

### Credential resolution diagnostics

| Command | Purpose |
|---|---|
| `aa_auto_sdr --show-config` | Show which credential source resolved (env / profile / .env / config.json) without exposing secrets. |
| `aa_auto_sdr --config-status` | Print the full credential resolution chain — every source checked, which one matched. Verbose. |
| `aa_auto_sdr --validate-config` | Resolve and validate credential shape **without** calling Adobe. Exit 0 on valid, 10 on missing fields or malformed `org_id`. |
| `aa_auto_sdr --sample-config` | Emit a `config.json` template to stdout. |

For the credential resolution model itself, see [`CONFIGURATION.md`](CONFIGURATION.md).

## Logging and observability

For the user-facing logging reference (events, log file naming, redaction), see [`LOGGING.md`](LOGGING.md). For the internal logger-call contract see [`LOGGING_STYLE.md`](LOGGING_STYLE.md).

| Flag | Behavior |
|----|----|
| `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` | Default: `INFO` (or `LOG_LEVEL` env var). |
| `--log-format {text,json}` | Output format for both console and file. `json` emits NDJSON. |
| `--quiet` / `-q` | Suppress progress banners and INFO console output. Errors and final paths still print. Log file is unaffected. |
| `--show-timings` | Print a per-stage timings block to stderr at end of run. Stages: `auth`, `resolve`, per-RSID `build:<rsid>`, per-format `write:<fmt>:<rsid>`, optional `snapshot:<rsid>`. |
| `--run-summary-json PATH \| -` | Emit a structured JSON run summary (started_at, finished_at, duration_seconds, tool_version, profile, per-RSID rsids, timings). Conflict: `--run-summary-json -` with `--output -` returns `OUTPUT` (15). |
| `--agent-mode` | Agent-friendly preset: defaults to `--format json --output - --log-format json` for options the user did not explicitly pass. `--output -` implies `--quiet`. |

```bash
uv run aa_auto_sdr <RSID> --log-format json --quiet
uv run aa_auto_sdr --batch demo.prod demo.staging --run-summary-json runs/$(date -u +%Y%m%dT%H%M%SZ).json
```

## Notion Integration

Publishes SDR reports to Notion as structured pages. Requires the optional extra and two env vars:

```bash
uv pip install 'aa-auto-sdr[notion]'
export NOTION_TOKEN=secret_...
export NOTION_PARENT_PAGE_ID=<page-id-of-parent>
```

The integration must be invited to the parent page (Notion: Share → Add connection). See [`CONFIGURATION.md`](CONFIGURATION.md#notion-integration-optional) for credential setup.

```bash
# Publish SDR directly to Notion
aa_auto_sdr examplersid1 --format notion

# Publish with custom output directory (registry stored there too)
aa_auto_sdr examplersid1 --format notion --output-dir ./reports

# Push existing JSON artifact to Notion (no AA API call)
aa_auto_sdr --push-to-notion ./reports/examplersid1.json

# Push an archived snapshot envelope
aa_auto_sdr --push-to-notion ~/.aa/orgs/acme/snapshots/examplersid1/2026-05-14T10-00-00Z.json

# Force a new Notion page even if one already exists for this RSID
aa_auto_sdr examplersid1 --format notion --notion-force-new
aa_auto_sdr --push-to-notion ./reports/examplersid1.json --notion-force-new

# Batch with Notion — serial only; --workers N>1 rejected with --format notion
aa_auto_sdr --batch examplersid1 examplersid2 --format notion
```

| Flag | Description |
|------|-------------|
| `--format notion` | Publish SDR to a Notion page as part of generation |
| `--push-to-notion FILE` | Push existing JSON/snapshot artifact to Notion (standalone mode) |
| `--notion-force-new` | Always create a new page, ignoring `.notion_pages.json` |

Re-runs update the existing Notion page in place. Page IDs are tracked in `.notion_pages.json` in the output directory (or the input file's parent for `--push-to-notion`). `--watch --format notion` and `--batch ... --format notion --workers N>1` are rejected at dispatch with `ExitCode.USAGE` — concurrent writes to the registry would race.

## Machine-readable errors

When `--output -` (generate JSON pipe) or `--format json|markdown --output -` (diff pipe) is in effect and an error occurs, a one-line JSON envelope writes to stderr:

```json
{"error":{"code":11,"type":"AuthError","message":"...","hint":"Verify credentials in Adobe Developer Console."}}
```

The envelope is stable; agent consumers can parse it without text matching.

## Fast-path actions

These complete in <100ms with no `pandas` / `aanalytics2` import:

| Command | Purpose |
|---|---|
| `aa_auto_sdr -V` / `--version` | Print the version. |
| `aa_auto_sdr -h` / `--help` | Print usage summary. |
| `aa_auto_sdr --exit-codes` | List every exit code with a one-line meaning. |
| `aa_auto_sdr --explain-exit-code <CODE>` | Paragraph explanation: meaning, likely causes, "What to try". |
| `aa_auto_sdr --completion {bash,zsh,fish}` | Emit a static shell-completion script. Redirect to your shell's completion dir. |

```bash
aa_auto_sdr --completion zsh > ~/.zsh/completions/_aa_auto_sdr
```
