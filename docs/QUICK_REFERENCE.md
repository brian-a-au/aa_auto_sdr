# Quick Reference

Single-page command cheat sheet for `aa_auto_sdr`. Grouped by mode, copy-paste ready. For per-flag semantics see [`CLI_REFERENCE.md`](CLI_REFERENCE.md); for the *why* behind each workflow see [`USE_CASES.md`](USE_CASES.md); for setup see [`INSTALLATION.md`](INSTALLATION.md) and [`CONFIGURATION.md`](CONFIGURATION.md).

> Commands below omit the `uv run` prefix for brevity. **macOS/Linux:** prepend `uv run`. **Windows:** activate the venv first (`.venv\Scripts\activate`), then run `aa_auto_sdr` directly.

## Modes

| Mode | Purpose | Default output |
|------|---------|----------------|
| **SDR Generation** | Document a report suite's dimensions, metrics, segments, calculated metrics, virtual report suites, and classification datasets | Excel (also CSV, JSON, HTML, Markdown, Notion, template-fill) |
| **Discovery** | List report suites and virtual report suites visible to your credentials | Table (also CSV, JSON) |
| **Inspection** | Drill into one report suite's components, metadata, or quick counts | Table (also CSV, JSON) |
| **Snapshot & Diff** | Capture a normalized snapshot and diff any two — version control for SDR | Console (also JSON, Markdown, PR-comment) |
| **Inventory Rollup** | Aggregate component counts across many report suites | Table (also CSV, JSON) |
| **Quality** | Severity-tagged naming and stale-component audits, promotable to a CI gate | Adds to the SDR; JSON/CSV report |

**SDR Generation** builds a Solution Design Reference — the full component inventory of one report suite. Use it for documentation, audits, and onboarding.

**Discovery** and **Inspection** explore what exists without building a full SDR. Use them for pre-SDR exploration, quick audits, and scripting.

**Snapshot & Diff** captures normalized state and reports what changed between any two points. Use it for change tracking, drift detection, and migration sign-off.

**Inventory Rollup** aggregates counts across report suites for an org-wide overview. Use it for landscape audits and governance.

**Quality** tags naming and staleness findings by severity and can fail a build. Use it for standardization and CI gates.

## Running commands

| Method | Command | Notes |
|--------|---------|-------|
| **uv run** | `uv run aa_auto_sdr ...` | Works immediately on macOS/Linux |
| **Activated venv** | `aa_auto_sdr ...` | After `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows) |

Both console entry points (`aa_auto_sdr` and `aa-auto-sdr`) are equivalent.

## SDR generation

```bash
# Single report suite by RSID
aa_auto_sdr demo.prod

# By report-suite name (case-insensitive exact match)
aa_auto_sdr "Adobe Store"

# Generate and open the file immediately
aa_auto_sdr demo.prod --open

# Auto-batch — two or more identifiers route to batch mode automatically
aa_auto_sdr rs1 rs2 rs3

# Mix RSIDs and names freely
aa_auto_sdr demo.prod "Adobe Store" demo.staging

# Explicit batch form (equivalent to auto-batch)
aa_auto_sdr --batch rs1 rs2 rs3 --output-dir /tmp/sdr

# Parallel batch, cancel pending work on first failure
aa_auto_sdr --batch rs1 rs2 rs3 --workers 4 --fail-fast

# Slim the SDR to one component family (skips excluded API calls)
aa_auto_sdr demo.prod --metrics-only
aa_auto_sdr demo.prod --dimensions-only

# Preview output paths without writing (auth still validates)
aa_auto_sdr demo.prod --dry-run

# Fill Adobe's official BRD/SDR template (see TEMPLATE_WORKFLOW.md)
aa_auto_sdr demo.prod --template ~/aa_en_BRD_SDR_template.xlsx
```

## Discovery & inspection

```bash
# List report suites / virtual report suites
aa_auto_sdr --list-reportsuites
aa_auto_sdr --list-virtual-reportsuites

# List as JSON for scripting
aa_auto_sdr --list-reportsuites --format json --output -

# Describe one report suite (metadata + per-component counts)
aa_auto_sdr --describe-reportsuite demo.prod

# Browse one component type at a time
aa_auto_sdr --list-metrics demo.prod
aa_auto_sdr --list-dimensions demo.prod
aa_auto_sdr --list-segments demo.prod
aa_auto_sdr --list-calculated-metrics demo.prod
aa_auto_sdr --list-classification-datasets demo.prod

# Filter, exclude, sort, limit (case-insensitive substring on name)
aa_auto_sdr --list-metrics demo.prod --filter page --sort name --limit 10
aa_auto_sdr --list-dimensions demo.prod --exclude test --sort name

# Pipe a component list to jq
aa_auto_sdr --list-dimensions demo.prod --format json --output - | jq '.[].name'

# Quick counts per report suite (lighter than --describe-reportsuite)
aa_auto_sdr --stats demo.prod
aa_auto_sdr --stats                      # every visible report suite

# Pick a report suite interactively, then feed it to another command
RSIDS=$(aa_auto_sdr --interactive --profile prod) && aa_auto_sdr $RSIDS --auto-snapshot --profile prod
```

## Snapshot & diff

```bash
# Capture a snapshot alongside generation (requires --profile)
aa_auto_sdr demo.prod --snapshot --profile prod

# Capture on every run
aa_auto_sdr demo.prod --auto-snapshot --profile prod

# Auto-snapshot with a retention policy
aa_auto_sdr demo.prod --auto-snapshot --auto-prune --keep-last 5 --profile prod
aa_auto_sdr demo.prod --auto-snapshot --auto-prune --keep-since 30d --profile prod

# List / prune snapshots
aa_auto_sdr --list-snapshots --profile prod
aa_auto_sdr --list-snapshots demo.prod --profile prod
aa_auto_sdr --prune-snapshots demo.prod --keep-last 10 --dry-run --profile prod

# Diff two snapshot files (no API calls)
aa_auto_sdr --diff a.json b.json

# Diff profile-scoped aliases (most common workflow)
aa_auto_sdr --diff demo.prod@latest demo.prod@previous --profile prod

# Diff at a specific timestamp, or against a git ref
aa_auto_sdr --diff demo.prod@2026-04-26T17-29-01+00-00 demo.prod@latest --profile prod
aa_auto_sdr --diff git:HEAD~1:snapshots/x.json git:HEAD:snapshots/x.json

# Diff to a JSON/Markdown pipe or PR-comment
aa_auto_sdr --diff a.json b.json --format json --output -
aa_auto_sdr --diff a.json b.json --format markdown --output diff.md
aa_auto_sdr --diff demo.prod@previous demo.prod@latest --profile prod --format pr-comment | pbcopy
```

**Diff token grammar:** bare path · `<rsid>@<timestamp>` · `<rsid>@latest` · `<rsid>@previous` · `git:<ref>:<path>`. Profile-form tokens need `--profile` or `--snapshot-dir`.

### Diff modifiers

| Flag | Effect |
|------|--------|
| `--changes-only` | Drop component types with no changes |
| `--summary` | Collapse to per-component-type counts only |
| `--side-by-side` | Before/after columns for modified fields (console) |
| `--diff-labels A=… B=…` | Override the "Source" / "Target" labels |
| `--show-only TYPES` | Restrict to listed types (e.g. `metrics,dimensions`) |
| `--max-issues N` | Cap each component's added/removed/modified rows |
| `--ignore-fields a,b` | Skip named fields during compare |
| `--extended-fields` | Include description/tags/category in compare (off by default) |
| `--quiet-diff` | Show only changed sections |
| `--reverse-diff` | Swap a and b before compare |
| `--warn-threshold N` | Exit `3` when total changes ≥ N (CI signal) |
| `--color-theme {default,accessible}` | Diff color palette |

## Trending, watch & git audit trail

```bash
# Rollup drift across a window of snapshots (reads snapshots, no API)
aa_auto_sdr demo.prod --trending-window 30d --profile prod
aa_auto_sdr rs1 rs2 rs3 --trending-window 30d --format json --profile prod

# Compare latest vs previous snapshot (sugar for @previous vs @latest)
aa_auto_sdr demo.prod --compare-with-prev --profile prod

# Watch loop — fetch, snapshot, diff each interval; NDJSON events on stdout
aa_auto_sdr demo.prod --watch --interval 1h --profile prod
aa_auto_sdr rs1 rs2 --watch --interval 6h --watch-threshold 5 --profile prod
aa_auto_sdr demo.prod --watch --interval 1h --agent-mode --profile prod | jq -c .

# Commit each snapshot to a git-versioned audit trail (auto-inits the dir)
aa_auto_sdr demo.prod --auto-snapshot --git-commit --profile prod
aa_auto_sdr demo.prod --watch --interval 1h --git-commit --git-push --profile prod
```

Watch event types: `baseline` (first cycle, always emitted), `change` (when `total_changes >= --watch-threshold`), `error` (per-RSID fetch failure — loop continues). SIGINT exits `0`.

## Inventory rollup

```bash
# Aggregate counts across every visible report suite
aa_auto_sdr --inventory-summary

# Across a selected set, as CSV
aa_auto_sdr rs1 rs2 rs3 --inventory-summary --format csv

# As machine-readable JSON
aa_auto_sdr --inventory-summary --format json
```

Reports totals plus min / max / avg per component type, with a per-RSID detail block.

## Quality engine

```bash
# Add naming-pattern and stale-component audits to the SDR
aa_auto_sdr demo.prod --audit-naming --flag-stale

# Emit a standalone machine-readable quality report
aa_auto_sdr demo.prod --audit-naming --quality-report json
aa_auto_sdr demo.prod --audit-naming --quality-report csv

# Fail CI when any issue is at or above a severity (exit 17)
aa_auto_sdr demo.prod --fail-on-quality HIGH

# Load defaults from a policy file (CLI flags always win)
aa_auto_sdr demo.prod --quality-policy ./policy.json
```

`--quality-report` or `--fail-on-quality` auto-enables both audits. Severities: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`.

## Profile management (multi-org)

```bash
# Create a profile per organization (interactive)
aa_auto_sdr --profile-add client-a
aa_auto_sdr --profile-add client-b

# List, show, test
aa_auto_sdr --profile-list
aa_auto_sdr --profile-show client-a
aa_auto_sdr --profile-test client-a          # live OAuth + getCompanyId()

# Use a profile
aa_auto_sdr --list-reportsuites --profile client-a
aa_auto_sdr "Main RS" -p client-b --format excel

# Import a profile non-interactively
aa_auto_sdr --profile-import client-c ./client-c.json
aa_auto_sdr --profile-import client-c ./client-c.json --profile-overwrite

# Set a default profile for the session
export AA_PROFILE=client-a
aa_auto_sdr --list-reportsuites              # uses client-a
```

Profiles live in `~/.aa/orgs/<name>/`. Snapshots are profile-scoped: `~/.aa/orgs/<name>/snapshots/<RSID>/<ts>.json`.

## Common options

| Option | Purpose | Applies to |
|--------|---------|------------|
| `-V`, `--version` | Print version and exit (fast-path) | All |
| `--profile NAME`, `-p` | Use a named profile from `~/.aa/orgs/` | All (when needed) |
| `--output-dir DIR` | Output directory for SDR files (default: cwd) | Generate |
| `--output PATH \| -` | File path, or `-` for stdout pipe | Generate (JSON), list/inspect, diff |
| `--format FMT` | Output format (per-action allowlist; see below) | All |
| `--filter`, `--exclude`, `--sort`, `--limit` | Shape list/inspect results | List/Inspect |
| `--open` | Open output in the OS default app after writing | Generate |
| `--dry-run` | Resolve and authenticate, print would-be paths, write nothing | Generate |
| `--metrics-only` / `--dimensions-only` | Slim the SDR to one component family | Generate |
| `--workers N` | Parallel batch workers (1..16, default 1) | Batch |
| `--fail-fast` | Cancel pending workers on first failure | Batch |
| `--sample N`, `--sample-seed N`, `--sample-stratified` | Subset RSIDs before dispatch | Batch |
| `--snapshot` / `--auto-snapshot` | Persist a snapshot (requires `--profile`) | Generate |
| `--auto-prune` + `--keep-last N` / `--keep-since DUR` | Retention policy | Snapshot |
| `--snapshot-dir PATH` | Override the active snapshot directory | Snapshot/Diff |
| `--name-match {exact,insensitive,fuzzy}` | Name-resolution strategy (default `insensitive`) | All |
| `--max-retries`, `--retry-base-delay`, `--retry-max-delay` | Tune transient-failure retries | All |
| `--log-level`, `--log-format {text,json}`, `--quiet` / `-q` | Logging controls | All |
| `--show-timings` | Per-stage timings to stderr at end of run | Generate |
| `--run-summary-json PATH \| -` | Structured JSON run summary | All |
| `--agent-mode` | Preset: `--format json --output - --log-format json` | All |
| `--yes` / `-y` | Skip confirmation prompts for destructive actions | Prune / Notion maintenance |

## Format support by mode

| Format | Generate | Diff | List/Inspect | Inventory | Description |
|--------|----------|------|--------------|-----------|-------------|
| `excel` | ✅ (default) | ❌ | ❌ | ❌ | Single workbook, one sheet per component type |
| `csv` | ✅ | ❌ | ✅ | ✅ | Comma-separated values |
| `json` | ✅ | ✅ | ✅ | ✅ | Machine-readable; jq pipelines |
| `html` | ✅ | ❌ | ❌ | ❌ | Self-contained static report |
| `markdown` | ✅ | ✅ | ❌ | ❌ | GFM; PR/wiki friendly |
| `notion` | ✅ (opt-in) | ❌ | ❌ | ❌ | Publish to a Notion page |
| `console` / `table` | ❌ | ✅ (default) | ✅ (default) | ✅ (default) | Terminal output |
| `pr-comment` | ❌ | ✅ | ❌ | ❌ | Compact GFM with collapsible `<details>` for GitHub PRs |

> The List/Inspect column covers `--describe-reportsuite` and the `--list-*` commands (table/json/csv). `--stats` is the exception: it supports `table` and `json` only.

### Format aliases (generation)

| Alias | Resolves to | Use case |
|-------|-------------|----------|
| `all` | excel + csv + json + html + markdown | Generate everything (archival) |
| `reports` | excel + markdown | Human-facing (Excel for analysts, Markdown for review) |
| `data` | csv + json | Machine-readable (spreadsheets + code) |
| `ci` | json + markdown | CI logs and PR comments |

`notion` is opt-in only and is not part of any alias.

## Quick recipes

```bash
# Pipe SDR JSON to jq
aa_auto_sdr demo.prod --format json --output - | jq '.report_suite'

# All five formats at once
aa_auto_sdr demo.prod --format all --output-dir ./reports

# JSON logging (for Splunk, ELK, CloudWatch)
aa_auto_sdr demo.prod --log-format json

# Output organized by date
aa_auto_sdr demo.prod --output-dir ./reports/$(date +%Y%m%d)

# Sample reproducibly from a large batch
aa_auto_sdr --batch rs1 rs2 rs3 rs4 rs5 --sample 2 --sample-seed 42

# Stratified sample by code prefix
aa_auto_sdr --batch prod.us prod.eu dev.us --sample 2 --sample-stratified

# Tune retries for a flaky org
aa_auto_sdr demo.prod --max-retries 6 --retry-base-delay 1.0 --retry-max-delay 30.0

# Machine-readable run summary
aa_auto_sdr demo.prod --run-summary-json ./summary.json

# Look up what an exit code means
aa_auto_sdr --explain-exit-code 17
```

## Environment variables

```bash
# Credentials (see CONFIGURATION.md for the full contract)
export ORG_ID="YOUR_ORG_ID@AdobeOrg"
export CLIENT_ID="YOUR_CLIENT_ID"
export SECRET="YOUR_CLIENT_SECRET"
export SCOPES="openid,AdobeID,additional_info.projectedProductContext"

# Optional
export AA_PROFILE=prod          # shorthand for --profile prod
export LOG_LEVEL=INFO

# Notion integration (for --format notion / --push-to-notion / registry)
export NOTION_TOKEN=secret_...
export NOTION_PARENT_PAGE_ID=<page-id>
export NOTION_REGISTRY_DATABASE_ID=<database-id>   # optional registry index
export NOTION_REGISTRY_COMPANY="Acme Corp"         # optional multi-org keying

# Console color policy
export NO_COLOR=1               # disable ANSI colors (https://no-color.org/)

# GitHub Actions job summary (usually set automatically)
export GITHUB_STEP_SUMMARY=/path/to/summary.md     # --diff auto-appends a render
```

## Setup & diagnostics

```bash
# Emit a config.json template
aa_auto_sdr --sample-config

# Show which credential source resolved
aa_auto_sdr --show-config

# Full credential resolution chain
aa_auto_sdr --config-status

# Validate credential shape locally (does not contact Adobe)
aa_auto_sdr --validate-config

# Confirm auth + scope + visibility against Adobe
aa_auto_sdr --list-reportsuites

# Shell tab-completion (static script)
aa_auto_sdr --completion bash >> ~/.bashrc
aa_auto_sdr --completion zsh > ~/.zsh/completions/_aa_auto_sdr
```

## Output files

| Format | File pattern | Description |
|--------|--------------|-------------|
| Excel | `<RSID>.xlsx` | 7-sheet workbook |
| CSV | `<RSID>.<component>.csv` | 7 files: dimensions, metrics, segments, calculated_metrics, virtual_report_suites, classifications, summary |
| JSON | `<RSID>.json` | Self-contained `SdrDocument` |
| HTML | `<RSID>.html` | Self-contained static report |
| Markdown | `<RSID>.md` | GFM, one H2 per component type |

**Excel sheet order:** 1. Summary · 2. Dimensions · 3. Metrics · 4. Segments · 5. Calculated Metrics · 6. Virtual Report Suites · 7. Classifications. Every sheet has a frozen header row and an autofilter. See [`OUTPUT_FORMATS.md`](OUTPUT_FORMATS.md) for full file layouts.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Generic error |
| 2 | Argument / usage error |
| 3 | Diff `--warn-threshold` exceeded (diff itself ran) |
| 10 | Bad config or missing credentials |
| 11 | Adobe OAuth Server-to-Server failure |
| 12 | Adobe Analytics API request failed |
| 13 | Report suite or resource not found |
| 14 | `--batch` partial success — some ok, some failed |
| 15 | Output writer failure |
| 16 | Snapshot resolve / schema / git failure |
| 17 | Quality gate breached (`--fail-on-quality`) |

Run `aa_auto_sdr --exit-codes` for the one-line table, or `aa_auto_sdr --explain-exit-code <CODE>` for full remediation. Source of truth: `src/aa_auto_sdr/core/exit_codes.py`.

## More information

- [Installation](INSTALLATION.md) — platform setup, install methods, optional extras
- [Configuration](CONFIGURATION.md) — credential sources, OAuth scopes, profiles, diagnostics
- [CLI Reference](CLI_REFERENCE.md) — every flag with semantics and examples
- [Use Cases & Best Practices](USE_CASES.md) — scenario playbooks, automation, CI/CD
- [Snapshot & Diff](SNAPSHOT_DIFF.md) — snapshot format, resolver tokens, diff semantics
- [Output Formats](OUTPUT_FORMATS.md) — formats, aliases, file layouts
- [Notion Setup](NOTION_SETUP.md) — Notion publishing and the SDR Registry
- [`AGENTS.md`](../AGENTS.md) — agent-mode contract for unattended runs
