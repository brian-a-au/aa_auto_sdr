# AGENTS.md — aa_auto_sdr Tool Contract

`aa_auto_sdr` generates Solution Design Reference (SDR) documentation from an Adobe Analytics report suite. **Read-only against the Adobe Analytics 2.0 API.** This tool never creates, updates, or deletes anything in your Adobe Analytics environment.

---

## Setup

```bash
uv sync
```

Python 3.14+ required. See [`README.md`](README.md) for first-time install.

### Auth: Environment Variables

| Variable    | Required | Description                                                                  |
|-------------|----------|------------------------------------------------------------------------------|
| `ORG_ID`    | Yes      | Adobe Organization ID                                                        |
| `CLIENT_ID` | Yes      | OAuth Client ID                                                              |
| `SECRET`    | Yes      | Client Secret                                                                |
| `SCOPES`    | Yes      | OAuth scopes (verified-minimum: `openid,AdobeID,additional_info.projectedProductContext`) |

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the canonical no-space comma-separated scope form and the four-source resolution chain.

### Auth: Profile Alternative

```bash
uv run aa_auto_sdr --profile-add <name>     # create interactively
uv run aa_auto_sdr --profile <name> ...     # use profile
export AA_PROFILE=<name>                    # set default
```

Profiles stored in `~/.aa/orgs/<name>/`. Profile overrides env vars.

---

## Command Reference

### Discovery

```bash
uv run aa_auto_sdr --list-reportsuites [--format json|csv] [--output -]
uv run aa_auto_sdr --list-virtual-reportsuites [--format json|csv] [--output -]
```

Supports `--filter PATTERN`, `--exclude PATTERN`, `--limit N`, `--sort FIELD`.

For per-RSID metadata + component counts, see `--describe-reportsuite` under Inspection below.

### Inspection (per report suite)

```bash
uv run aa_auto_sdr --describe-reportsuite      <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-metrics              <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-dimensions           <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-segments             <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-calculated-metrics   <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-classification-datasets <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --stats [<RSID>...]                          [--format json]
```

Supports `--filter`, `--exclude`, `--sort`, `--limit`.

### Generation

| Format value | Output produced                       |
|--------------|---------------------------------------|
| `excel`      | `.xlsx` workbook (default)            |
| `csv`        | CSV file(s)                           |
| `json`       | JSON file                             |
| `html`       | HTML report                           |
| `markdown`   | Markdown file                         |
| `all`        | All five file formats                 |
| `reports`    | Alias: excel + markdown               |
| `data`       | Alias: csv + json                     |
| `ci`         | Alias: json + markdown                |

```bash
# Single SDR (default Excel)
uv run aa_auto_sdr <RSID>

# Single SDR, JSON, custom dir
uv run aa_auto_sdr <RSID> --format json --output-dir /reports

# Batch (auto-detected from 2+ positionals; --batch flag preserved for back-compat)
uv run aa_auto_sdr <RSID1> <RSID2> <RSID3> --format ci

# Run summary for observability
uv run aa_auto_sdr <RSID> --format json --run-summary-json -
```

### Parallel batch

`aa_auto_sdr --batch <RSID...>` accepts `--workers N` (1..16, default 1)
to run per-RSID SDR generation in parallel via a `ThreadPoolExecutor`.

- `--workers 1` (default): sequential, single-threaded.
- `--workers N>=2`: parallel run via the worker pool.
- `--fail-fast` opts out of the continue-on-error default on both paths:
  sequential runs stop at the first failure; parallel runs cancel pending
  workers. Unattempted RSIDs are recorded as cancelled failures. Fail-fast
  also covers the identifier-resolution phase: the first identifier that
  fails to resolve stops the batch, and the identifiers after it are recorded
  as cancelled. Without `--fail-fast`, every unresolvable identifier is
  reported in one run.

JSON log records on parallel runs include `worker_id` (the per-RSID
submission index, 0..N-1). Sequential runs omit the field. Agents
parsing logs should treat the field as optional.

Continue-on-error is the batch default; no opt-in flag is needed. Cache sharing across workers is not implemented; cache is per-process and gated by `--enable-cache`.

`--batch --format notion --workers N>1` is supported. A process-level lock serializes all `.notion_pages.json` writes so concurrent workers do not race. Note Notion's ~3 req/s API rate limit; the client retries HTTP 429 responses automatically, but high worker counts may increase latency on large batches.

### Validation cache

`--enable-cache`, `--clear-cache`, `--cache-ttl SECONDS`, `--cache-size
ENTRIES` flags wire through to a `ValidationCache` instance. The quality
severity engine is the production caller; cache keys include the
severity-table version so mapping changes invalidate. DEBUG log records
emit `cache_event=hit/miss/evict/expire`.

### Quality audits

`aa_auto_sdr <RSID> --audit-naming` adds a `quality.naming_audit` block
to the SDR document with case-style counts, prefix groupings, and
recommendations.

`aa_auto_sdr <RSID> --flag-stale` adds a `quality.stale_components`
block listing components matching stale-keyword / version-suffix /
date-pattern regexes.

Both flags are independent (either alone, or both together). Default
behavior (both off) leaves the `quality` field as `None` (absent from
JSON output).

Snapshot envelope schema is `aa-sdr-snapshot/v4`. Older majors (`v1`,
`v2`, `v3`) remain readable with missing fields defaulted. See
`CHANGELOG.md` for the per-version field additions.

### Name resolution

`aa_auto_sdr <RSID_OR_NAME>` accepts `--name-match {exact,insensitive,fuzzy}` (default: `insensitive`).

- `exact`: literal RSID match, then exact-case name match.
- `insensitive` (default): literal RSID, then case-insensitive name match.
- `fuzzy`: insensitive first; falls back to SequenceMatcher at threshold 0.85.

Multi-match in `exact` / `fuzzy` mode raises `AmbiguousMatchError` with exit code 13 (`NOT_FOUND`); the candidate list is rendered to stderr. `insensitive` mode returns all matches (the CLI then generates per-RSID).

### Diff field shaping

`aa_auto_sdr --diff <a> <b> --extended-fields` includes noisy fields
(description, tags, category, etc.) in diff output. Without the flag,
these fields are suppressed by default — diff output focuses on
identity, structure, and definition changes.

### Batch sampling

`aa_auto_sdr --batch <RSID...>` accepts three sampling flags that
subset the batch list before dispatch. All three require `--batch`;
passing them outside `--batch` exits with `USAGE` (2).

| Flag | Type | Effect |
|------|------|--------|
| `--sample N` | int (>=1) | Subset N RSIDs from the batch list. `N >= len(batch)` is a no-op (full list runs, `BatchResult.sampled=False`). |
| `--sample-seed N` | int | Integer RNG seed for reproducible sampling. Default: non-deterministic. |
| `--sample-stratified` | bool flag | Group RSIDs by code prefix (split on first `.` / `_` / `-`) and sample proportionally per group. Without the flag, sampling is uniform random. |

When sampling actually applies, the batch summary banner prints
`Sampled X of Y RSIDs (strategy=random[, seed=N])`, the run emits a
`batch_sampled` INFO log record (carrying `count`, `count_total`,
`sample_size`, `sample_seed`, `sample_strategy`), and `BatchResult`
records `sampled=True` along with `sample_size`, `sample_seed`, and
`total_available` fields. JSON-summary consumers can read those
fields directly.

Per-RSID SDR documents and snapshots are unaffected by sampling — it only changes which RSIDs run, not what each run produces.

### Inventory summary

`aa_auto_sdr [<RSID>...] --inventory-summary` emits a cross-RSID aggregate rollup of component counts (totals, min, max, avg per component type) plus a per-RSID detail block. With no positional RSIDs, summarizes every visible report suite (mirrors `--stats`). Uses the `count_only` fetcher path — no full SDR build.

| Flag combination | Effect |
|------------------|--------|
| `--inventory-summary` | Aggregate over every visible RS. Table output (default). |
| `--inventory-summary <RSID...>` | Aggregate over the supplied RSIDs only. |
| `--inventory-summary --format table\|json\|csv` | Pick output format. Other formats (excel, html, markdown, all) error with `OUTPUT` (15). |

`--inventory-summary` lives in the same argparse `actions` mutex
group as `--stats`, `--describe-reportsuite`, and the list-actions, so
combining it with any other action returns a clean argparse error
(no manual precedence in `cli/main.py`).

Per-RSID fetch failures mark the affected components with `*` in table output; the JSON form attaches a `fetch_status` map to the per-RSID row. Mirrors `--stats` exactly.

### Quality severity engine

Naming audits (`--audit-naming`, `--flag-stale`) are severity-tagged and machine-readable; three flags promote them into a CI gate.

| Flag | Effect |
|------|--------|
| `--quality-report {json,csv}` | Emit a standalone quality report alongside SDR output. Default filename `quality_report_<RSID>_<timestamp>.{json,csv}`. |
| `--quality-policy <path>` | Load a JSON policy file. Top-level keys: `fail_on_quality`, `quality_report`. CLI flags always win over policy values. Hyphen / underscore canonicalization; optional `quality_policy` / `quality` envelope nesting. |
| `--fail-on-quality {CRITICAL,HIGH,MEDIUM,LOW,INFO}` | Exit `ExitCode.QUALITY` (17) if any issue at or above the threshold exists. SDR output and snapshot still emit normally. |

Severity ladder (most severe first):

| Severity | Source | Examples |
|----------|--------|----------|
| CRITICAL | (reserved) | future use |
| HIGH | (reserved) | future use |
| MEDIUM | `stale_keyword` | test, old, deprecated, legacy, obsolete, unused |
| LOW | `stale_keyword`, `version_suffix`, `date_pattern`, `case_inconsistency` | temp, backup, copy, archive; `_v2`; `_20240101`; mixed case styles |
| INFO | (reserved) | future use |

Behavior:

- **Auto-enable.** `--quality-report` or `--fail-on-quality` without
  `--audit-naming` / `--flag-stale` auto-enables both audits.
- **Mode-scoping.** Quality flags outside SDR generation (`--stats`,
  the discovery/inspection list-actions, `--inventory-summary`,
  `--diff`) exit `USAGE` (2).
- **Batch precedence.** `PARTIAL_SUCCESS` (14) outranks `QUALITY` (17).
  Build failures are more actionable than quality verdicts; users
  fixing partial failures re-run and then see the gate.
- **Cache.** `quality.run_audits` is the production caller of `ValidationCache`. Cache key includes the severity-table version so mapping changes invalidate.

Note on `--max-issues`: there are *two* concepts with the same surface name. The CLI flag `--max-issues N` for `--diff` rendering is real and valid (caps per-component added/removed/modified counts in the rendered diff). The policy-file key `max_issues` (and `allow_partial`) are NOT supported keys in `--quality-policy` files — the loader rejects them with `ConfigError`.

### Drift / trending windows

Apply the snapshot comparator across a window of snapshots for one or
more RSIDs. Reads existing snapshot files only — no AA API contact, no
SDR rebuild, no auth required. Two new actions; both are mutually
exclusive with the rest of the actions group.

| Flag | Effect |
|------|--------|
| `--trending-window <DURATION>` | Per-RSID time-series of component lifecycle counts plus a derived drift summary. Duration grammar `Nh|Nd|Nw` (e.g. `30d`, `12h`, `4w`). Multi-RSID supported via positionals. |
| `--compare-with-prev` | Sugar over `--diff <RSID>@previous <RSID>@latest`. Multi-RSID loops; worst exit code wins. Reuses the diff resolver, output formats, and flag set. |
| `--snapshot-dir <PATH>` | Override the active profile's snapshot directory. Composes with `--trending-window`; other snapshot-aware actions still resolve from `--profile` only. |

Examples:

```bash
# 30-day drift window for one report suite (console output, default)
uv run aa_auto_sdr <RSID> --trending-window 30d --profile prod

# 30-day drift across three RSIDs as JSON for dashboards
uv run aa_auto_sdr rs1 rs2 rs3 --trending-window 30d --format json --profile prod

# Latest vs previous snapshot for one report suite
uv run aa_auto_sdr <RSID> --compare-with-prev --profile prod
```

Output formats: `console` (default), `json` (schema `aa-trending/v1`),
`markdown`. Multi-RSID renders per-RSID blocks (console / markdown) or
wraps in `{"reports": [...]}` (json).

Drift summary (always included; no opt-in flag) carries:

- `total_changes` — sum of added + removed + modified across all pairs.
- `volatility_score` — `total_changes / (starting_components * n_pairs)`,
  clamped to `[0.0, 1.0]`. 0.0 = stable; 1.0 = fully churned per pair.
- `most_active_component_type` — type with the highest churn over the
  window (or `null` if zero churn).
- `churn_by_component_type` — per-type counts.

Behavior:

- `--trending-window` requires positional RSIDs (no auto-discover); no
  positional → `USAGE` (2).
- Empty window for one RSID → warning + `PARTIAL_SUCCESS` (14); empty
  for all RSIDs → `NOT_FOUND` (13).
- Window upper bound is "now at compute time," not "the most recent
  snapshot's timestamp."
- Suppressed component sections (degraded / partial fetches) contribute zeros to drift counts so degraded snapshots don't inflate scores.

Drift in `aa_auto_sdr` is per-RSID lifecycle churn and is always included in `--trending-window` output; no separate opt-in flag is needed.

### Watch mode

`aa_auto_sdr <RSID>... --watch --interval <duration>` enters a foreground
monitoring loop. Each cycle: fetch the report suite, save a snapshot, diff
vs the previous snapshot, and emit one NDJSON event on stdout. The loop
runs until SIGINT / SIGTERM (exit 0) or an unrecoverable fatal error. Per-cycle
fetch failures emit `error` events and continue the loop — they do not
terminate it. `--watch-threshold N` (default `1`) sets the minimum total
change count to trigger a `change` event; `--watch-threshold 0` emits every
cycle including zero-change cycles (heartbeat mode).

```bash
# Watch one report suite every hour; pipe events to jq
uv run aa_auto_sdr rs_prod_us --watch --interval 1h --agent-mode | jq -c .

# Watch multiple RSIDs every 6 hours; threshold of 5 changes before emitting
uv run aa_auto_sdr rs_prod_us rs_prod_eu --watch --interval 6h --watch-threshold 5

# Heartbeat mode — emit every cycle even when nothing changed
uv run aa_auto_sdr rs_prod_us --watch --interval 1d --watch-threshold 0

# Route events to a file while keeping stderr logs
uv run aa_auto_sdr rs_prod_us --watch --interval 1h --log-format json > events.ndjson
```

Event types (schema `aa-watch-event/v1`, NDJSON on stdout):

- `baseline` — first cycle for an RSID; always emitted (no prior snapshot to diff against).
- `change` — subsequent cycle where `total_changes >= watch_threshold`.
- `error` — per-RSID fetch failure within a cycle; loop continues.

SIGINT / SIGTERM → exit 0. `--quality-policy` and `--fail-on-quality` are rejected when paired with `--watch` (exit `USAGE` 2). `--interval` or non-default `--watch-threshold` without `--watch` are also rejected (exit `USAGE` 2).

`--watch --format notion` is supported. Notion publishes on the baseline cycle and on every `change` event. Zero-change cycles and fetch-error cycles do not publish. If the Notion API raises during a cycle, a `notion_watch_publish_failed` WARNING fires and the loop continues.

### Notion standalone modes

Two maintenance modes operate without generating SDRs. Both default to **preview** (no changes) and require `--yes` to apply changes.

| Flag | Exit on success | What it does |
|------|-----------------|--------------|
| `--notion-prune-orphans` | `OK` (0) | Preview: print orphaned page ids. With `--yes`: archive each page in `.notion_pages.json`'s `superseded` list (Notion trash, recoverable). |
| `--notion-repair-database` | `OK` (0) | Preview: print missing and conflicting properties. With `--yes`: additively create missing properties in the registry database. Requires `NOTION_REGISTRY_DATABASE_ID` or `--notion-registry-database`. |
| `--notion-create-database` | `OK` (0) | Preview: print the planned title and parent page. With `--yes`: create the SDR Registry database with the full canonical schema under `NOTION_PARENT_PAGE_ID` and print the new database id. Requires `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID`. Standalone mode: exits `USAGE` (2) if combined with generation, `--batch`, `--push-to-notion`, `--diff`, `--watch`, `--notion-prune-orphans`, or `--notion-repair-database`. |
| `--notion-database-title NAME` | — | Override the title of the database created by `--notion-create-database` (default: `AA SDR Registry`). Exits `USAGE` (2) without `--notion-create-database`. |

```bash
# Dry-run preview
uv run aa_auto_sdr --notion-prune-orphans
uv run aa_auto_sdr --notion-repair-database
uv run aa_auto_sdr --notion-create-database

# Apply
uv run aa_auto_sdr --notion-prune-orphans --yes
uv run aa_auto_sdr --notion-repair-database --yes
uv run aa_auto_sdr --notion-create-database --yes

# Create with a custom title
uv run aa_auto_sdr --notion-create-database --notion-database-title "Acme SDR Registry" --yes
```

Without `--yes`, all three modes only preview and make no changes (including on non-tty stdin); pass `--yes` to apply. All modes require the `[notion]` extra and `NOTION_TOKEN`. `--notion-repair-database` additionally requires a database id. `--notion-create-database` additionally requires `NOTION_PARENT_PAGE_ID`.

### Template-fill Excel writer

Hands-on workflow guide: [`docs/TEMPLATE_WORKFLOW.md`](docs/TEMPLATE_WORKFLOW.md) — covers first-run, batch, snapshot/git composition, coverage map, and the five `template_*` log events used as health signals in unattended runs.

| Flag | Semantics |
|------|-----------|
| `--template PATH` | Path to an existing `.xlsx` template. Switches the Excel writer to fill-mode for the run. Required readable `.xlsx`; missing/dir/non-`.xlsx` → USAGE (2). Routes resolved `excel` formats to `excel-template`. Composes with `--batch`. Rejected with `--watch`, `--diff`, list/inspect actions, and naturally rejected by `--agent-mode` (no `excel` in agent-mode's forced format set). |
| `--template-organization NAME` | Organization string written to `Glossary!C2`. Defaults to report suite name. Requires `--template`. |

**Dropped flags (v1.16.0 roadmap):**

- `--template-overwrite-reserved` — dropped from the v1.16.0 roadmap. Per the
  spec: match-by-id is the uniform rule, customer-edited descriptions should
  be re-applied after generation. argparse-rejected if passed.

### Git integration

Commit each snapshot to a git-versioned audit trail under the snapshot
directory. The directory IS the git repo — initialized on first use, no
explicit setup step.

```bash
# Commit each snapshot from a single SDR build.
uv run aa_auto_sdr <RSID> --git-commit

# Commit and push.
uv run aa_auto_sdr <RSID> --git-commit --git-push

# Custom commit message.
uv run aa_auto_sdr <RSID> --git-commit --git-message "Audit trail: release 2.3"

# Inside a watch loop — closes the agent-native loop.
uv run aa_auto_sdr <RSID> --watch --interval 1h --git-commit --git-push
```

**Auto-init:** First `--git-commit` on a non-repo directory runs:
`git init --initial-branch=main`, `git config --local commit.gpgsign false`,
writes `README.md`, creates the initial commit.

**Remote configuration:** Run `git remote add origin <url>` inside the
snapshot directory before using `--git-push`. We do not manage
credentials or remotes.

**Composition:**
- `--git-commit` is a modifier; it requires an SDR-generating action
  (bare RSID, `--batch`, or `--watch`). Pairing with `--diff`,
  `--stats`, `--list-X`, `--trending-window`, `--compare-with-prev`, or
  `--inventory-summary` is rejected (USAGE 2).
- `--git-push` requires `--git-commit` (USAGE 2 otherwise).
- `--git-message` requires `--git-commit` (USAGE 2 otherwise).

**Watch composition:** Each cycle that emits a `baseline` or `change`
event also commits. NDJSON event payload gains an optional `git` block
on success:

```json
{"schema": "aa-watch-event/v1", "event": "change", "cycle": 7,
 "rsid": "rs_a", "started_at": "…", "ended_at": "…",
 "snapshot_path": "rs_a/2026-05-11T15-00-00+00-00.json",
 "summary": {},
 "git": {"committed": true, "commit_sha": "abc1234567…", "pushed": true}}
```

On git failure, the original baseline/change event emits first (with no
`git` block), followed by a separate `error` event:

```json
{"schema": "aa-watch-event/v1", "event": "error", "cycle": 7,
 "rsid": "rs_a", "started_at": "…", "ended_at": "…",
 "error_type": "GitPushError", "error": "remote rejected: …"}
```

The watch loop never dies on git failure — per-cycle errors continue
the loop (same posture as fetch errors).

**Batch composition.** Each RSID's snapshot commits as a separate commit
(pathspec-scoped to `<rsid>/`). Workers are serialized for git operations
regardless of `--workers` setting. Per-RSID git failures surface in
`RunResult.git_op` and on stderr; if any RSID's git operation fails but
every SDR succeeded, the batch exits `PARTIAL_SUCCESS` (14) instead of
`OK` (0). The batch-precedence rule still holds: `PARTIAL_SUCCESS` outranks
`QUALITY`, and an all-failed batch surfaces the last failure's exit code.

**Dropped flags (for parity with cja):**
- `--git-init` — replaced by lazy auto-init on first `--git-commit`.
- `--git-push-on-change` — reduces to `--git-push` (commit already
  short-circuits on no-diff).

### Comparison / Diff

```bash
# Live diff of two snapshots (paths, snapshot specs, or git refs)
uv run aa_auto_sdr --diff <a> <b> [--format json] [--output -]
```

Diff inputs accept paths, `<rsid>@<ts>|@latest|@previous`, and `git:<ref>:<path>`.

Key flags: `--changes-only`, `--summary`, `--show-only TYPES`, `--max-issues N`, `--side-by-side`, `--quiet-diff`, `--diff-labels A=… B=…`, `--reverse-diff`, `--ignore-fields description,tags`, `--warn-threshold N`. PR-comment renderer: `--format pr-comment`. CI integration: `$GITHUB_STEP_SUMMARY` auto-append for `--diff` runs.

### Snapshots

```bash
# Save a snapshot alongside generation (requires --profile)
uv run aa_auto_sdr <RSID> --profile <name> --snapshot

# Auto-snapshot + retention (per-RSID; requires --profile)
uv run aa_auto_sdr <RSID> --profile <name> --auto-snapshot --auto-prune --keep-last 20 --keep-since 30d

# List / prune snapshots (both require --profile)
uv run aa_auto_sdr --profile <name> --list-snapshots [<RSID>]
uv run aa_auto_sdr --profile <name> --prune-snapshots --keep-last 20 --dry-run
uv run aa_auto_sdr --profile <name> --prune-snapshots --keep-since 30d --yes
```

Snapshot lifecycle commands all require `--profile` — snapshots are stored under `~/.aa/orgs/<profile>/snapshots/`. Per-RSID retention semantics. `--prune-snapshots` requires `--yes` for non-tty stdin (or `--dry-run`); refuses with `USAGE` (2) otherwise.

### Diagnostics

```bash
uv run aa_auto_sdr --version                      # alias: -V
uv run aa_auto_sdr --exit-codes                   # full exit-code list
uv run aa_auto_sdr --explain-exit-code <CODE>     # human-readable explanation
uv run aa_auto_sdr --completion {bash,zsh,fish}   # shell completion script
```

### Validation

```bash
# Shape-only validation, no Adobe API call
uv run aa_auto_sdr --validate-config

# Full credential resolution chain (text output)
uv run aa_auto_sdr --config-status

# Full-pipeline auth-and-resolve dry run (requires <RSID>)
uv run aa_auto_sdr <RSID> --dry-run
```

---

## Exit Codes

| Code | Meaning                                                     | Agent Action                                       |
|------|-------------------------------------------------------------|----------------------------------------------------|
| `0`  | Success                                                     | Continue; consume stdout output                    |
| `1`  | Generic / uncategorized failure                             | Abort; parse stderr JSON for `error`/`error_type`  |
| `2`  | Argument / usage error                                      | Abort; check `--help`                              |
| `3`  | Diff `--warn-threshold` exceeded (diff itself ran OK)       | Notify; optionally escalate                        |
| `10` | Bad config / missing credentials                            | Abort; run `--config-status` or `--validate-config` |
| `11` | OAuth Server-to-Server failure                              | Abort; verify scopes, integration profile          |
| `12` | Adobe Analytics API request failed                          | Retry if transient                                 |
| `13` | Report suite or other resource not found                    | Abort; verify RSID                                 |
| `14` | Batch ran with mixed success and failure                    | Flag for review; consume per-RSID summary          |
| `15` | Output writer failure (filesystem / format mismatch / mutex)| Abort; check `--output-dir` perms, `--output -` mutex with `--run-summary-json -` |
| `16` | Snapshot resolve / schema / git failure                     | Abort; verify snapshot path / git ref              |
| `17` | Quality gate breached: `--fail-on-quality` threshold exceeded | SDR + snapshot still emitted; consume `quality.summary` from output |
| `130`| KeyboardInterrupt (SIGINT)                                  | Treat as cancelled; retry if appropriate           |

Exit code 1 takes precedence over 2 if both apply. Use `--explain-exit-code CODE` for runtime lookup.

---

## Output Conventions

- Use `--format json --output -` for machine-parseable stdout where supported.
- Machine-readable stdout uses `json` or `csv` (where supported by the command family).
- `--output -` implies `--quiet` (banner/progress and INFO records on stderr suppressed; errors, warnings, and final result paths still print; the per-run log file is unaffected). Same for `--run-summary-json -`.
- Under `--agent-mode`, the preset always applies the implicit `--output -` *before* the per-command-family resolver suppresses it for file-only formats (single SDR / batch). The implicit `--quiet` is derived from that pre-suppression output, so `aa_auto_sdr <RSID> --agent-mode --format excel` runs silently on stderr even though the SDR artifact is written to a file. This is the intended UX for unattended runs. For verbose stderr under agent-mode, pass `--log-level DEBUG` (widens the file logger; the console stays quiet by contract). `--quiet=false` is not a supported override — for verbose stderr you must avoid the implicit `--output -` by passing a non-stdout `--output PATH` (or, for SDR generation, simply omit `--agent-mode`).
- On failure, **stderr** receives a JSON error envelope:
  ```json
  {"error": "Configuration error: Missing credentials", "error_type": "ConfigError"}
  ```
- `--run-summary-json PATH` writes a structured run summary to file or stdout (`-`). Generate / batch only — discovery, inspect, and diff routes ignore it.
- **Mutex:** `--run-summary-json -` + `--output -` exits `OUTPUT` (15) before any work. `--agent-mode` applies the implicit `--output -`, so explicit `--run-summary-json -` triggers this on generate / batch routes.
- `--explain-exit-code CODE` writes the explanation to stdout (always). It is a fast-path action that does not interact with `--run-summary-json` or `--agent-mode`.

For unattended runs against the live AA API, tune retry behavior with:

```bash
aa_auto_sdr <RSID> --max-retries 6 --retry-base-delay 1.0 --retry-max-delay 30.0
```

Defaults: `--max-retries 3`, `--retry-base-delay 0.5`, `--retry-max-delay 10.0`.
Retries fire on transient SDK failures (the spike-confirmed shape — `KeyError`/
`ValueError` from indexing into urllib3-stub error responses, plus
`requests.ConnectionError`/`Timeout`); permanent failures (auth, validation,
unknown RSID) surface immediately. Retry attempts emit `retry_attempt` DEBUG
records under `--log-format json` so log aggregation can quantify retries
per run.

**Note on stall budget.** `aanalytics2` performs its own urllib3-level retries
inside each outer attempt (3 internal retries, i.e. 4 attempts, with
`backoff_factor=1`, hardcoded). Our `--max-retries` runs *outside* that, so the worst-case
HTTP-request count for a hard-failing endpoint scales as
`(urllib3_retries + 1) × (--max-retries + 1)`. At the default `--max-retries 3`
that's up to 16 requests; at `--max-retries 6` it's up to 28. Wall-clock
stalls scale similarly because urllib3 honors `Retry-After` and exponential
backoff. Tune `--max-retries` deliberately for unattended runs where total
budget matters.

All fetchers — including VRS — use this single-rung formula. (An earlier reduced-expansion fallback rung doubled the VRS budget; it was retired because the SDK's `extended_info=False` rows lack `parentRsid` and the rung could only ever return empty.)

### `fetch_status` field on inspect/stats JSON output

`--describe-reportsuite` and `--stats` JSON output gains an optional
per-record `fetch_status` field that mirrors the snapshot envelope's
`degraded_components` / `partial_components` semantics. Shape:

```json
{
  "rsid": "demo.prod",
  "virtual_report_suites": 0,
  "classifications": 5,
  "fetch_status": {
    "virtual_report_suites": {
      "status": "degraded",
      "expansion_level": null
    }
  }
}
```

- Field absent when all components are healthy (additive — back-compat).
- Plural component-type keys: `"virtual_report_suites"`, `"classifications"`.
- `status` enum: `"degraded"` (no data) | `"partial"` (data at reduced
  expansion).
- `expansion_level` is `null` for `degraded`, a string for `partial`.

For text-format consumers, the equivalent signal is a `*` marker on the
count cell + a footer line; `--list-classification-datasets` emits a
stderr banner.

---

## VRS Fetch Degradation

When Adobe's `/reportsuites/virtualreportsuites` endpoint fails (after the configured retry budget exhausts, or immediately on a permanent endpoint-shape error), `aa_auto_sdr` degrades gracefully: the SDR is generated with an empty VRS list and the snapshot envelope records the degradation. The structured `expansion_level` field carries `full` on the success INFO record and `exhausted` / `count_only` on the failure WARNING. There is no reduced-expansion fallback — the SDK's `extended_info=False` rows lack `parentRsid`, so a minimal call cannot be attributed to a report suite.

**Snapshot signalling.** Degraded-fetch snapshots carry `degraded_components` markers in the envelope (`partial_components` remains in the schema and is still honored when reading snapshots written by earlier releases); the diff comparator suppresses sections with mismatched fetch quality rather than rendering false-modified VRS rows. Pre-`v2` snapshots load forward-compat as if all components were healthy.

**Envelope keys for agent introspection.** Current (`v4`) snapshots
carry two fetch-status keys directly accessible via `jq`:

- `.degraded_components` — list of component-type names whose fetch
  returned no data (e.g., `["classifications"]`).
- `.partial_components` — dict mapping component-type name to expansion
  level (e.g., `{"virtual_report_suites": "minimal"}` in snapshots written
  by earlier releases; current releases no longer produce partial fetches
  but the key remains present and honored by `--diff`).

Both keys are always present (empty `[]` / `{}` when nothing is
degraded). Pre-`v2` snapshots lack these keys; the loader fills them
in-memory at load time. The `v4` envelope additionally carries a
`quality` block (`issues`, `summary`) — empty when the quality engine
was not run.

---

## File Conventions

| Artifact      | Location                                                         | Override flag                                                |
|---------------|------------------------------------------------------------------|--------------------------------------------------------------|
| SDR reports   | Current directory (default)                                      | `--output-dir PATH`                                          |
| Snapshots     | `~/.aa/orgs/<profile>/snapshots/<RSID>/<ts>.json` (per-RSID)     | `--profile NAME` (selects the profile-scoped snapshot store) |
| Log output    | `logs/` (per-run rotating files, 10 MB / 5 backups)              | `--log-level`, `--log-format {text,json}`, `--quiet`         |
| Profiles      | `~/.aa/orgs/<name>/`                                             | `--profile NAME`, `AA_PROFILE` env                           |

Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Log formats: `text` (default), `json` (NDJSON for Splunk/ELK/Datadog).

---

## Agent Integration

### `--agent-mode` Preset

`--agent-mode` is a convenience preset that defaults the following options when the user did not pass them explicitly:

```
--format json --output - --log-format json
```

Explicit user choices always win — `--agent-mode --format excel` keeps `excel`.

```bash
# Direct stdout command families:
uv run aa_auto_sdr --list-reportsuites --agent-mode
uv run aa_auto_sdr --diff <a> <b> --agent-mode
uv run aa_auto_sdr --list-metrics <RSID> --agent-mode

# Single / batch SDR keep --output-dir semantics; the preset still applies --log-format json
uv run aa_auto_sdr <RSID> --agent-mode --output-dir /reports
```

Config preflight before running unattended:

```bash
uv run aa_auto_sdr --validate-config                     # shape-only, no API call
uv run aa_auto_sdr --config-status                       # full credential resolution chain
```

### Command-Family Applicability

| Command Family            | `--agent-mode` | Notes |
|---------------------------|----------------|-------|
| Single SDR                | Limited        | Preset applies for `--log-format json`; `--output -` is suppressed (no stdout-capable format); artifacts are written under `--output-dir DIR` (default cwd). **`--output PATH` is silently ignored for SDR generation** — only `--output-dir DIR` controls the artifact destination. To override the destination under agent-mode, pass `--output-dir /path/to/dir`. |
| Batch SDR                 | Limited        | Same as Single SDR — `--output-dir DIR` controls destination, `--output PATH` ignored. One artifact set per RSID. |
| Discovery / Inspection    | ✅              | JSON or CSV on stdout; prefer exact RSIDs for unattended inspection. |
| Diff Family               | ✅              | JSON on stdout for `--diff` (the only stdout-capable diff format under the agent contract). PR-comment markdown (`--format pr-comment`) also writes to stdout when `--output PATH` is omitted — the agent-mode preset's implicit `--output -` does not suppress this, since `output=None` and `output="-"` follow the same stdout-write code path in the diff command. Agents using `--format pr-comment` should pipe to a file, pass an explicit `--output PATH`, or use `$GITHUB_STEP_SUMMARY` (auto-append on CI). |
| Stats                     | ✅              | JSON on stdout (`--format json`). |
| Validation / Preflight    | Partial        | Both `--config-status` (text) and `--validate-config` are exit-code driven. No JSON output mode today; use exit codes for branching. |
| Fast-Path Flags           | Partial        | `--version`, `--exit-codes`, `--explain-exit-code`, `--completion {bash,zsh,fish}` are detected positionally (must be first on argv). Place them before `--agent-mode`, e.g. `aa_auto_sdr --version` or `aa_auto_sdr --exit-codes`. Forms like `aa_auto_sdr --agent-mode --version` fall through to argparse and error with `unrecognized arguments`. The agent-mode preset is intentionally not applied for fast-path flags — they exit before logging or output resolution. |
| Snapshots (list / prune)  | Partial        | `--profile <name> --list-snapshots --format json --output -` supported (lifecycle commands require `--profile`). `--prune-snapshots` requires `--yes` for non-tty stdin (or `--dry-run`); refuses with `USAGE` (2) otherwise. |

### Exact-ID Guidance

Prefer exact RSIDs over names for unattended automation. Name resolution costs an extra API call and is subject to ambiguity (multi-name match emits a user-facing line). Use `--list-reportsuites --format json --output -` to resolve names to RSIDs in a preflight step.

### Preflight Pattern

```bash
# 1. Validate config (no API call, fast)
uv run aa_auto_sdr --validate-config

# 2. Resolve names to exact RSIDs
RSIDS=$(uv run aa_auto_sdr --list-reportsuites --agent-mode | jq -r '.[].rsid')

# 3. Run the actual command with exact IDs
uv run aa_auto_sdr $RSIDS --agent-mode --output-dir /reports
```

---

## Releasing

Releasing is a human-initiated action; agent-mode and unattended runs never publish. The tool is read-only against Adobe Analytics, and cutting a release is the one workflow that writes outside the repo (it uploads to PyPI). See [`RELEASING.md`](RELEASING.md) for the runbook: bump `src/aa_auto_sdr/core/version.py` and `CHANGELOG.md`, merge to `main`, tag `vX.Y.Z`, and publish a GitHub Release — [`.github/workflows/release.yml`](.github/workflows/release.yml) then builds and uploads to PyPI over OIDC, with no token and no manual upload step.

## See Also

- [`RELEASING.md`](RELEASING.md) — how to cut a release and publish to PyPI (human-initiated)
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — credential resolution chain, profile layout, scopes
- [`README.md`](README.md) — human-facing CLI tour
- [`docs/LOGGING_STYLE.md`](docs/LOGGING_STYLE.md) — structured-fields vocabulary used by `--log-format json`
- [`CLAUDE.md`](CLAUDE.md) — design constraints (read-only, API 2.0 only, no shared core with `cja_auto_sdr`)
- `--exit-codes` / `--explain-exit-code CODE` — runtime exit-code lookup
