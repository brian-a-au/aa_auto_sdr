# CLI Reference

Every flag and what it does. For onboarding, see [`QUICKSTART.md`](QUICKSTART.md).

## Generation

### `aa_auto_sdr <RSID-or-name>`

Generate one SDR for a report suite. Positional argument accepts an RSID exact-match or a report-suite name (case-insensitive exact match). When a name matches multiple suites, an SDR is produced for each.

```bash
uv run aa_auto_sdr dgeo1xxpnwcidadobestore
uv run aa_auto_sdr "Adobe Store" --format json --output-dir /tmp/sdr
```

Default format: Excel. Output filename keys off the canonical RSID.

Exit codes: `0` (success), `10` (config), `11` (auth), `12` (api), `13` (rs not found), `15` (output error).

### `aa_auto_sdr <RSID...> [<NAME>...]` — auto-batch (v1.1)

Pass two or more identifiers and the tool automatically routes to batch mode — no `--batch` flag needed. **RSIDs and names may be mixed freely** in a single invocation; per-RSID name resolution happens inside the batch loop.

```bash
# Three RSIDs
uv run aa_auto_sdr rs1 rs2 rs3 --output-dir /tmp/sdr

# Mixed RSIDs and names
uv run aa_auto_sdr dgeo1xxpnwcidadobestore "Adobe Store" demo.prod --format json

# Auto-batch + auto-snapshot
uv run aa_auto_sdr rs1 "Adobe Store" --profile prod --auto-snapshot --auto-prune --keep-last 5
```

`--output -` is rejected when more than one identifier is given (multi-SDR cannot share one stream → exit 15). Same continue-on-error semantics, summary banner, and partial-success exit code as explicit `--batch`.

### `aa_auto_sdr --batch RSID1 RSID2 ...`

Original v0.5 form — kept for backward compatibility. Sequential generation across multiple report suites. Continue-on-error: a per-RSID failure does not stop the rest. After the run, a CJA-style summary banner prints counts, success rate, total bytes/duration, and per-RSID ✓/✗ rows.

```bash
uv run aa_auto_sdr --batch RS1 RS2 RS3 --format json --output-dir /tmp/sdr
```

Mutually exclusive with positional RSIDs (use one form or the other; mixing them returns exit 2). `--output -` is rejected (multiple SDRs cannot share one stream → exit 15).

Exit codes: `0`, `14` (partial — some succeeded, some failed), or the last failure's exit code if all failed.

## Discovery

### `aa_auto_sdr --list-reportsuites`

List every report suite visible to the org's credentials.

### `aa_auto_sdr --list-virtual-reportsuites`

Same shape, for virtual report suites.

Both accept `--filter STR`, `--exclude STR`, `--sort FIELD`, `--limit N`, `--format json|csv` (default: fixed-width table to stdout), `--output PATH|-`.

## Inspection

### `aa_auto_sdr --describe-reportsuite <RSID-or-name>`

Print metadata + per-component counts (no full SDR built).

### `aa_auto_sdr --list-{metrics,dimensions,segments,calculated-metrics,classification-datasets} <RSID>`

Lists one component type for one RS. Same options as discovery: `--filter`, `--exclude`, `--sort`, `--limit`, `--format`, `--output`.

```bash
uv run aa_auto_sdr --list-metrics demo.prod --filter page --sort name --limit 10
```

## Diff (snapshot comparison)

### `aa_auto_sdr --diff <a> <b>`

Compute a structured diff between two snapshot envelopes. Each token is one of:

| Token form | Example | Resolution |
|----|----|----|
| File path | `./snap-a.json` | Read JSON, validate v1 schema, compare. |
| `<rsid>@<timestamp>` | `demo.prod@2026-04-26T17-29-01+00-00` | Look in `~/.aa/orgs/<profile>/snapshots/<rsid>/`. |
| `<rsid>@latest` | `demo.prod@latest` | Most-recent file in that dir. |
| `<rsid>@previous` | `demo.prod@previous` | Second-most-recent file. |
| `git:<ref>:<path>` | `git:HEAD~1:snapshots/x.json` | `git show <ref>:<path>` from cwd. |

Profile-form tokens (`<rsid>@<spec>`) require `--profile`.

`--format console|json|markdown|pr-comment` (default `console`). `--output -` for json/markdown/pr-comment pipes; rejected for console (use `--format json|markdown` for pipes).

```bash
uv run aa_auto_sdr --diff demo.prod@latest demo.prod@previous --profile prod
uv run aa_auto_sdr --diff a.json b.json --format json --output -
uv run aa_auto_sdr --diff git:HEAD~1:snap.json git:HEAD:snap.json
```

#### v1.1 diff modifiers

- `--side-by-side` — render modified-component fields with before/after columns (console). Markdown's existing layout already includes Before/After columns; the flag is a no-op there.
- `--summary` — collapse output to per-component-type counts only; suppress per-item / per-field detail. Honored by all four diff renderers.
- `--ignore-fields description,tags` — comma-separated field names to skip during compare. Match is exact at every nesting level (e.g., skips `segments[*].definition.description` too). Filtering happens in the comparator, so the resulting `DiffReport` is clean for piped JSON consumers.
- `--format pr-comment` — compact GFM with collapsible `<details>` blocks, optimized for pasting into a GitHub PR comment. Length-capped at 60K chars (GitHub comment limit is 65,536); truncates at the last `</details>` boundary with a banner.

```bash
uv run aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --summary
uv run aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --format pr-comment | pbcopy
uv run aa_auto_sdr --diff a.json b.json --ignore-fields description,tags
```

Exit codes: `0` (diff ran — even if it shows changes), `15` (bad format/output combo), `16` (snapshot resolve / schema / git failure).

## Snapshot

### `<RSID> --snapshot --profile <name>`

Persist the built SDR to `~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-timestamp>.json` alongside the format outputs. Requires `--profile`. Works on `<RSID>` and `--batch`.

```bash
uv run aa_auto_sdr <RSID> --profile prod --snapshot
uv run aa_auto_sdr --batch RS1 RS2 --profile prod --snapshot
```

`--snapshot --output -` works — the snapshot is an out-of-band side effect.

### `<RSID> --auto-snapshot --profile <name>` (v1.1)

Like `--snapshot` but designed to be set as a default for every run — no need to remember the flag each time. Combines with `--snapshot` to a single save (no double-write). Requires `--profile`.

```bash
uv run aa_auto_sdr <RSID> --profile prod --auto-snapshot
uv run aa_auto_sdr --batch RS1 RS2 --profile prod --auto-snapshot
```

### `<RSID> --auto-prune --keep-last N | --keep-since DURATION` (v1.1)

After auto-saving (or alongside `--prune-snapshots`), apply a retention policy and delete older snapshots per RSID. Requires `--profile` and exactly one of `--keep-last` or `--keep-since`. Currently a silent no-op if `--auto-snapshot` (or `--snapshot`) isn't also set — wire either to make pruning actually run.

- `--keep-last N` — keep the N most recent snapshots **per RSID** (delete the rest).
- `--keep-since DURATION` — keep snapshots newer than DURATION. Format: `<int><h|d|w>` (e.g., `30d`, `12h`, `4w`). Bad format → exit 10.

```bash
uv run aa_auto_sdr <RSID> --profile prod --auto-snapshot --auto-prune --keep-last 5
uv run aa_auto_sdr --batch RS1 RS2 --profile prod --auto-snapshot --auto-prune --keep-since 30d
```

### `aa_auto_sdr --list-snapshots [<RSID>] --profile <name>` (v1.1)

List snapshots in the profile's snapshot dir. Optional positional `<RSID>` narrows to one suite.

- `--format table` (default): fixed-width columns `RSID`, `CAPTURED_AT`, `PATH`.
- `--format json`: `[{"rsid", "captured_at", "path"}, ...]`. `captured_at` is canonical ISO-8601 (with colons), suitable for `jq` / `datetime.fromisoformat`.

```bash
uv run aa_auto_sdr --list-snapshots --profile prod
uv run aa_auto_sdr --list-snapshots RS1 --profile prod --format json | jq '.[].captured_at'
```

Exit codes: `0`, `10` (no profile or unknown profile), `15` (bad format value).

### `aa_auto_sdr --prune-snapshots [<RSID>] --keep-last N | --keep-since DURATION --profile <name>` (v1.1)

Apply the retention policy and delete snapshots that fail the keep test. Per-RSID — `--keep-last 5` keeps 5 *per RSID*, not 5 total.

- `--dry-run` — list deletions without unlinking.

```bash
uv run aa_auto_sdr --prune-snapshots --profile prod --keep-last 10 --dry-run
uv run aa_auto_sdr --prune-snapshots RS1 --profile prod --keep-since 90d
```

Exit codes: `0`, `10` (no profile / no policy / bad keep-since format).

**v1.2.1 behavior:** on non-interactive stdin without `--yes` the command
now refuses with exit code 2 (`USAGE`), not exit 0. Pass `--yes`,
pipe `yes |`, or run from a tty.

## Profile / config

### `aa_auto_sdr --profile-add <name>`

Interactive prompt; writes `~/.aa/orgs/<name>/config.json`.

### `aa_auto_sdr --profile <name>`

Use a named profile for credentials.

### `aa_auto_sdr --profile-list` (v1.1)

List profile names in `~/.aa/orgs/`. `--format json` for scripts.

### `aa_auto_sdr --profile-show <NAME>` (v1.1)

Print profile fields with `client_id` masked and `secret` never shown. Includes a count of snapshots stored under that profile. Exit 10 if profile not found.

### `aa_auto_sdr --profile-test <NAME>` (v1.1)

Authenticate the named profile (full OAuth + `getCompanyId()` round trip) and print PASS/FAIL. Exit 0 on PASS, 10 on config error, 11 on auth failure. Useful for diagnosing scope / Admin Console issues without running a full SDR.

```bash
uv run aa_auto_sdr --profile-test prod
# PASS: profile 'prod' authenticated; company_id=...
```

### `aa_auto_sdr --profile-import <NAME> <FILE>` (v1.1)

Import a JSON file (with `org_id`, `client_id`, `secret`, `scopes` fields) as a new profile. Exit 10 on missing file, bad JSON, or missing required fields.

**Breaking change in v1.2:** errors with exit 10 if the profile already exists. Pass `--profile-overwrite` to allow replacement.

### `aa_auto_sdr --show-config`

Show which credential source resolved (env / profile / .env / config.json) without exposing secrets.

### `aa_auto_sdr --config-status` (v1.2)

Print the full credential resolution chain — every source checked, which one matched. More verbose than `--show-config`. Useful for debugging why a profile isn't being picked up.

```text
Resolution chain (highest precedence first):
  1. --profile=prod              ✓ MATCHED
  2. env vars                     ⊘ skipped
  3. .env (cwd)                   ⊘ skipped
  4. config.json (cwd)            ⊘ skipped

Resolved values (sensitive fields masked):
  org_id:    abc@AdobeOrg
  client_id: 1234…5678
  ...
```

### `aa_auto_sdr --validate-config` (v1.2)

Resolve credentials and validate shape **without** calling Adobe. Fast pre-flight check. Exit 0 on valid shape, exit 10 on missing fields or malformed `org_id` (must end with `@AdobeOrg`).

### `aa_auto_sdr --sample-config` (v1.2)

Emit a `config.json` template to stdout. Pipe to a file:

```bash
aa_auto_sdr --sample-config > config.json
```

## Discovery & UX (v1.2)

### `aa_auto_sdr --stats [<RSID>...]` (v1.2)

Quick component counts per RSID — no full SDR build, no metadata. Lighter than `--describe-reportsuite`. With no positional args, lists every visible report suite.

- `--format table` (default): `RSID  NAME  DIM  MET  SEG  CALC  VRS  CLS`
- `--format json`: `[{"rsid", "name", "counts": {...}}, ...]`

### `aa_auto_sdr --interactive` (v1.2)

Print a numbered menu of visible report suites to stderr, prompt for selection by index or `all` on stdin, emit the chosen RSID(s) to stdout. Designed for shell composition:

```bash
RSIDS=$(aa_auto_sdr --interactive --profile prod) && aa_auto_sdr $RSIDS --auto-snapshot
```

Exit 130 on Ctrl-C. Exit 2 (USAGE) on out-of-range index.

## Diff polish (v1.2)

These flags refine the existing `--diff` output without changing its core behavior. They compose with v1.1's `--side-by-side`, `--summary`, `--ignore-fields`.

| Flag | Behavior |
|------|----------|
| `--quiet-diff` | Suppress unchanged trailers; show only changed sections (console + markdown) |
| `--diff-labels A=… B=…` | Override "Source" / "Target" labels in renderer output |
| `--reverse-diff` | Swap a and b before compare |
| `--warn-threshold N` | Exit 3 (`WARN`) if total changes ≥ N. Diff itself still runs. |
| `--changes-only` | In rendered output, drop component types with no changes |
| `--show-only TYPES` | Restrict diff output to listed types (CSV: `metrics,dimensions`) |
| `--max-issues N` | Cap each component's added/removed/modified to N items in render |

```bash
aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --quiet-diff --warn-threshold 10
aa_auto_sdr --diff a.json b.json --diff-labels "A=baseline" "B=candidate"
aa_auto_sdr --diff a.json b.json --show-only metrics --max-issues 20
```

**`$GITHUB_STEP_SUMMARY` (v1.2):** when the env var is set (GitHub Actions does this automatically per job), every `--diff` invocation also appends a markdown render to that file. No flag needed; uses the full unfiltered report.

## Generation modifiers (v1.2)

### `<RSID> --metrics-only` / `--dimensions-only` (mutex)

Slim the SDR by skipping the API calls for excluded component types. Real perf win for large RSes.

```bash
aa_auto_sdr <RSID> --metrics-only --format json --output-dir /tmp/metrics-only
```

`--metrics-only` and `--dimensions-only` are mutually exclusive. These flags **cannot** be combined with `--snapshot` or `--auto-snapshot` (filtered snapshots produce misleading diffs against full ones — exit 2).

### `<RSID> --dry-run` / `--batch RS1 RS2 --dry-run` (v1.2)

Resolve credentials, authenticate, resolve RSID/name → canonical RSIDs, then **print what would be written** without doing the heavy component fetch or any file writes. Auth still validates so the user knows the run would succeed.

```bash
aa_auto_sdr <RSID> --dry-run --auto-snapshot --profile prod
# DRY RUN — would generate:
#   demo.prod.xlsx
#   ~/.aa/orgs/prod/snapshots/demo.prod/2026-04-27T...json
# (no files were written; remove --dry-run to execute)
```

### `<RSID> --open` (v1.2)

After successful generation, open the first output file (single) or output dir (batch) in the OS default app. Best-effort — silently skips on headless / no-display environments.

### `--yes` / `-y` (v1.2)

Skip confirmation prompts on destructive actions. Currently only `--prune-snapshots` (without `--dry-run`) prompts. Non-tty stdin (CI / pipes) refuses to prompt and aborts safely without `--yes`.

## Observability (v1.2.1)

### `--show-timings`

Print a per-stage timings block to stderr at end of a `<RSID>` or `--batch`
run. Stages: `auth`, `resolve`, per-RSID `build:<rsid>`, per-format
`write:<fmt>:<rsid>`, optional `snapshot:<rsid>`. Format is fixed-width
(32-char label, right-aligned `{:.3f}s`, trailing `Total`).

Example:

    uv run aa_auto_sdr demo.prod --show-timings

### `--run-summary-json PATH`

Emit a structured JSON summary of the run to `PATH` (or `-` for stdout).
Includes `started_at`, `finished_at`, `duration_seconds`, `tool_version`,
`profile`, per-RSID `rsids` (rsid, name, succeeded, formats, output_paths,
snapshot_path, error), and `timings` (populated only when `--show-timings`
is also set; otherwise an empty list).

Use cases: CI artifact, downstream tooling (e.g. PR-comment generators,
dashboards), audit trail.

Conflict: `--run-summary-json -` combined with `--output -` returns
`OUTPUT` (15) before any work happens, since both want stdout.

Example:

    uv run aa_auto_sdr --batch demo.prod demo.staging --run-summary-json runs/$(date -u +%Y%m%dT%H%M%SZ).json

## Fast-path actions

These complete in <100ms with no `pandas`/`aanalytics2` import:

### `aa_auto_sdr -V` / `--version`
Print the version.

### `aa_auto_sdr -h` / `--help`
Print usage summary.

### `aa_auto_sdr --exit-codes`
List every exit code with a one-line meaning.

### `aa_auto_sdr --explain-exit-code <CODE>`
Paragraph-form explanation of one exit code: meaning, likely causes, "What to try".

### `aa_auto_sdr --completion {bash,zsh,fish}`
Emit a static shell-completion script. Redirect to your shell's completion dir.

```bash
aa_auto_sdr --completion zsh > ~/.zsh/completions/_aa_auto_sdr
```

## Common options

| Flag | Applies to | Behavior |
|----|----|----|
| `--format FMT` | generate, list/inspect, diff | Per-action allowlist (excel/csv/json/html/markdown for generate; json/csv for list/inspect; console/json/markdown for diff). |
| `--output PATH \| -` | list/inspect, diff | File path, or `-` for stdout pipe (where supported). |
| `--output-dir DIR` | generate, batch | Output directory for SDR file(s). Default: cwd. |
| `--filter STR` | list/inspect | Case-insensitive substring on `name`. |
| `--exclude STR` | list/inspect | Case-insensitive substring exclusion on `name`. |
| `--sort FIELD` | list/inspect | Sort by allowlisted field per command. |
| `--limit N` | list/inspect | Cap output to N records. |
| `--profile NAME` | all (when needed) | Use named profile for credentials. Required for `<rsid>@<spec>` diff tokens and `--snapshot`. |
| `--snapshot` | generate, batch | Persist SDR snapshot under the profile's snapshot dir. |

## Exit codes

| Code | Meaning |
|----|----|
| 0 | Success |
| 1 | Generic error |
| 2 | Argument / usage error (argparse) |
| 3 | Diff `--warn-threshold` exceeded (diff itself ran successfully; v1.2) |
| 10 | Bad config or missing credentials |
| 11 | Adobe OAuth Server-to-Server failure |
| 12 | Adobe Analytics API request failed |
| 13 | Report suite or other resource not found |
| 14 | `--batch` partial success — some ok, some failed |
| 15 | Output writer failure |
| 16 | Snapshot resolve / schema / git failure |

For per-code details:

```bash
aa_auto_sdr --explain-exit-code 11
```

## Machine-readable errors

When `--output -` (generate JSON pipe) or `--format json|markdown --output -` (diff pipe) is in effect and an error occurs, a one-line JSON envelope writes to stderr:

```json
{"error":{"code":11,"type":"AuthError","message":"...","hint":"Verify credentials in Adobe Developer Console."}}
```

Stdout stays silent so downstream `jq` etc. sees empty input.
