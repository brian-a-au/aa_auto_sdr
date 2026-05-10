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

### Parallel batch (v1.8.0+)

`aa_auto_sdr --batch <RSID...>` accepts `--workers N` (1..16, default 1)
to run per-RSID SDR generation in parallel via a `ThreadPoolExecutor`.

- `--workers 1` (default): byte-equivalent sequential behavior as in v1.7.2.
- `--workers N>=2`: parallel run; `--fail-fast` opts out of the
  continue-on-error default and cancels pending workers on first
  exception.

JSON log records on parallel runs include `worker_id` (the per-RSID
submission index, 0..N-1). Sequential runs omit the field. Agents
parsing logs should treat the field as optional.

Three flags listed in the public roadmap were deliberately removed during
v1.8.0 spec design (see CHANGELOG):
- `--continue-on-error` (existing default; flag would be redundant)
- `--shared-cache` (no implementation under threads)
- `--use-cache` (redundant with `--enable-cache`)

Attempting to pass any of these returns a standard argparse "unrecognized
argument" error.

### Validation cache (dormant)

`--enable-cache`, `--clear-cache`, `--cache-ttl SECONDS`, `--cache-size
ENTRIES` flags wire through to a `ValidationCache` instance. The cache
target is empty in v1.8.0 — the class ships now to lock the API and
flag surface ahead of v1.12.0's quality engine, which will be the first
caller. DEBUG log records emit `cache_event=hit/miss/evict/expire` from
the cache class itself; production code paths see neither hits nor misses
in v1.8.0.

### Quality audits (v1.9.0+)

`aa_auto_sdr <RSID> --audit-naming` adds a `quality.naming_audit` block
to the SDR document with case-style counts, prefix groupings, and
recommendations.

`aa_auto_sdr <RSID> --flag-stale` adds a `quality.stale_components`
block listing components matching stale-keyword / version-suffix /
date-pattern regexes.

Both flags are independent (either alone, or both together). Default
behavior (both off) preserves v1.8.0 byte-equivalence — `quality` field
is `None` and absent from the JSON output.

Snapshot envelope schema is bumped to `aa-sdr-snapshot/v3`. v1 and v2
envelopes remain readable.

### Name resolution (v1.9.0+)

`aa_auto_sdr <RSID_OR_NAME>` accepts `--name-match {exact,insensitive,fuzzy}`
(default: `insensitive`). The default preserves pre-v1.9.0 case-insensitive
name matching.

- `exact`: literal RSID match, then exact-case name match.
- `insensitive`: literal RSID, then case-insensitive name match
  (DEFAULT).
- `fuzzy`: insensitive first; falls back to SequenceMatcher at threshold
  0.85.

Multi-match in `exact` / `fuzzy` mode raises `AmbiguousMatchError` with
exit code 13 (`NOT_FOUND`); the candidate list is rendered to stderr.
`insensitive` mode preserves pre-v1.9.0 behavior of returning all
matches (CLI generates per-RSID).

### Diff field shaping (v1.9.0+)

`aa_auto_sdr --diff <a> <b> --extended-fields` includes noisy fields
(description, tags, category, etc.) in diff output. Without the flag,
these fields are suppressed by default — diff output focuses on
identity, structure, and definition changes.

Four flags listed in the public roadmap were deliberately removed during
v1.9.0 spec design (see CHANGELOG):
- `--no-component-types` (CJA-only concept)
- `--lock-stale-threshold` (CJA org-report lock)
- `--include-names` (AA includes by default)
- `--include-metadata` (AA includes by default)

Attempting to pass any of these returns the standard argparse
"unrecognized argument" error.

### Batch sampling (v1.10.0+)

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

Per-RSID SDR documents and snapshots are byte-identical to v1.9.0;
sampling only changes which RSIDs run, not what each run produces.

Two flags listed in the public roadmap were deliberately removed
during v1.10.0 spec design (see CHANGELOG):
- `--memory-limit` (CJA-only — guards a cross-DV index aa doesn't build)
- `--memory-warning` (same rationale)

Attempting to pass either returns the standard argparse
"unrecognized argument" error.

### Inventory summary (v1.11.0+)

`aa_auto_sdr [<RSID>...] --inventory-summary` emits a cross-RSID
aggregate rollup of component counts (totals, min, max, avg per
component type) plus a per-RSID detail block. With no positional
RSIDs, summarizes every visible report suite (mirrors `--stats`).
Reuses the v1.7.2 `count_only` fetcher path — no new SDK surface.

| Flag combination | Effect |
|------------------|--------|
| `--inventory-summary` | Aggregate over every visible RS. Table output (default). |
| `--inventory-summary <RSID...>` | Aggregate over the supplied RSIDs only. |
| `--inventory-summary --format table\|json\|csv` | Pick output format. Other formats (excel, html, markdown, all) error with `OUTPUT` (15). |

`--inventory-summary` lives in the same argparse `actions` mutex
group as `--stats`, `--describe-reportsuite`, and the list-actions, so
combining it with any other action returns a clean argparse error
(no manual precedence in `cli/main.py`).

Per-RSID fetch failures mark the affected components with `*` in
table output; the JSON form attaches a `fetch_status` map to the
per-RSID row. Mirrors `--stats` exactly.

One flag listed in the public roadmap was deliberately removed
during v1.11.0 spec design (see CHANGELOG):
- `--inventory-only` (CJA-only — aa's SDR document treats segments
  and calculated metrics as first-class sections; aa already has
  `--metrics-only` / `--dimensions-only` and the list-actions
  inspection commands)

Attempting to pass it returns the standard argparse "unrecognized
argument" error.

### Quality severity engine (v1.12.0+)

The v1.9.0 naming audits (`--audit-naming`, `--flag-stale`) are now
severity-tagged and machine-readable. Three new flags promote them
into a CI gate.

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
- **Cache.** `quality.run_audits` is the first production caller of
  the v1.8.0 `ValidationCache`. Cache key includes the severity-table
  version so v1.12.x mapping changes invalidate.

Two cja policy keys are NOT supported and are rejected by the policy
loader with an explicit `ConfigError`:

- `--max-issues` / `max_issues` policy key (cja's per-component cap;
  aa's quality block is compact — promoted v1.9.0 findings only)
- `--allow-partial` / `allow_partial` policy key (aa already has
  `PARTIAL_SUCCESS` (14) and `QUALITY` (17) as orthogonal codes)

Note: the unrelated `--max-issues` flag for `--diff` rendering predates
v1.12.0 and remains valid; only the *policy* key of the same name is
rejected.

### Drift / trending windows (v1.13.0+)

Apply the snapshot comparator across a window of snapshots for one or
more RSIDs. Reads existing snapshot files only — no AA API contact, no
SDR rebuild, no auth required. Two new actions; both are mutually
exclusive with the rest of the actions group.

| Flag | Effect |
|------|--------|
| `--trending-window <DURATION>` | Per-RSID time-series of component lifecycle counts plus a derived drift summary. Duration grammar `Nh|Nd|Nw` (e.g. `30d`, `12h`, `4w`). Multi-RSID supported via positionals. |
| `--compare-with-prev` | Sugar over `--diff <RSID>@previous <RSID>@latest`. Multi-RSID loops; worst exit code wins. Reuses the diff resolver, output formats, and flag set. |
| `--snapshot-dir <PATH>` | Override the active profile's snapshot directory. Composes with `--trending-window`; other snapshot-aware actions still resolve from `--profile` only in v1.13.0. |

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
- Suppressed component sections (degraded / partial fetches) contribute
  zeros to drift counts so degraded snapshots don't inflate scores.

Roadmap deviation (dropped):

- **`--include-drift` is rejected.** cja's `--include-drift` is a
  cross-data-view org-report toggle; aa has no org-report. Drift in aa
  is per-RSID lifecycle churn, computed from the existing comparator
  and always included in `--trending-window` output. The flag would
  either duplicate that output or invent an aa-specific score gated
  behind redundant opt-in. Argparse rejects it with the standard
  unrecognized-argument error.

### Watch mode (v1.14.0)

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

SIGINT / SIGTERM → exit 0. `--format`, `--quality-policy`, and
`--fail-on-quality` are rejected when paired with `--watch` (exit `USAGE` 2).
`--interval` or non-default `--watch-threshold` without `--watch` are also
rejected (exit `USAGE` 2).

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
inside each outer attempt (4 internal retries with `backoff_factor=1`,
hardcoded). Our `--max-retries` runs *outside* that, so the worst-case
HTTP-request count for a hard-failing endpoint scales as
`(urllib3_retries + 1) × (--max-retries + 1)`. At the default `--max-retries 3`
that's up to 16 requests; at `--max-retries 6` it's up to 28. Wall-clock
stalls scale similarly because urllib3 honors `Retry-After` and exponential
backoff. Tune `--max-retries` deliberately for unattended runs where total
budget matters.

**VRS doubles this budget.** `fetch_virtual_report_suites` runs the v1.7.0
reduced-expansion ladder as two sequential retry rungs (full → minimal),
and each rung consumes the full `--max-retries` budget independently.
So VRS worst case is `2 × (urllib3_retries + 1) × (--max-retries + 1)` —
up to **32 requests** at default, **56** at `--max-retries 6`. Other
fetchers (dimensions / metrics / segments / calculated metrics /
classifications / report-suite / VRS-summary discovery) use the
single-rung formula above.

### `fetch_status` field on inspect/stats JSON output (v1.7.2+)

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

## VRS Reduced Expansion

When Adobe's `/reportsuites/virtualreportsuites` endpoint fails on the full
expansion request (after the configured retry budget exhausts), `aa_auto_sdr`
v1.7.0+ falls back to a minimal-expansion call (`extended_info=False`) so the
SDR still gets a partial VRS list. The structured `expansion_level` field on
the `component_fetch` INFO record carries `full` / `minimal` / `exhausted` so
operators can spot when an org is hitting the fallback. A separate
`vrs_expansion_fallback` WARNING fires for the minimal/exhausted paths.

**Snapshot caveat — closed in v1.7.1.** Snapshots taken at
`expansion_level=minimal` (and degraded-fetch snapshots) now carry
`partial_components` / `degraded_components` markers in the envelope; the
diff comparator suppresses sections with mismatched fetch quality rather
than rendering false-modified VRS rows. Pre-v1.7.1 (`v1` schema) snapshots
load forward-compat as if all components were healthy.

**Envelope keys for agent introspection.** v2 snapshots carry two
fetch-status keys directly accessible via `jq`:

- `.degraded_components` — list of component-type names whose fetch
  returned no data (e.g., `["classifications"]`).
- `.partial_components` — dict mapping component-type name to expansion
  level (e.g., `{"virtual_report_suites": "minimal"}`).

Both keys are always present in v2 envelopes (empty `[]` / `{}` when
nothing is degraded). v1 envelopes (taken under v1.7.0 or earlier) lack
these keys; the loader fills them in-memory at load time.

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

## See Also

- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — credential resolution chain, profile layout, scopes
- [`README.md`](README.md) — human-facing CLI tour
- [`docs/LOGGING_STYLE.md`](docs/LOGGING_STYLE.md) — structured-fields vocabulary used by `--log-format json`
- [`CLAUDE.md`](CLAUDE.md) — design constraints (read-only, API 2.0 only, no shared core with `cja_auto_sdr`)
- `--exit-codes` / `--explain-exit-code CODE` — runtime exit-code lookup
