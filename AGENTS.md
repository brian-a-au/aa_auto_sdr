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
uv run aa_auto_sdr --describe-reportsuite <RSID_OR_NAME>
```

Supports `--filter PATTERN`, `--exclude PATTERN`, `--limit N`, `--sort FIELD`.

### Inspection (per report suite)

```bash
uv run aa_auto_sdr --list-metrics              <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-dimensions           <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-segments             <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-calculated-metrics   <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --list-classification-datasets <RSID_OR_NAME> [--format json|csv] [--output -]
uv run aa_auto_sdr --stats [<RSID>...]                          [--format json] [--output -]
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

### Comparison / Diff

```bash
# Live diff of two snapshots (paths, snapshot specs, or git refs)
uv run aa_auto_sdr --diff <a> <b> [--format json] [--output -]
```

Diff inputs accept paths, `<rsid>@<ts>|@latest|@previous`, and `git:<ref>:<path>`.

Key flags: `--changes-only`, `--summary`, `--show-only TYPES`, `--max-issues N`, `--side-by-side`, `--quiet-diff`, `--diff-labels A=… B=…`, `--reverse-diff`, `--ignore-fields description,tags`, `--warn-threshold N`. PR-comment renderer: `--format pr-comment`. CI integration: `$GITHUB_STEP_SUMMARY` auto-append for `--diff` runs.

### Snapshots

```bash
# Save a snapshot alongside generation
uv run aa_auto_sdr <RSID> --snapshot

# Auto-snapshot + retention (per-RSID)
uv run aa_auto_sdr <RSID> --auto-snapshot --auto-prune --keep-last 20 --keep-since 30d

# List / prune snapshots
uv run aa_auto_sdr --list-snapshots [<RSID>]
uv run aa_auto_sdr --prune-snapshots --keep-last 20 --dry-run
uv run aa_auto_sdr --prune-snapshots --keep-since 30d --yes
```

Per-RSID retention semantics. `--prune-snapshots` requires `--yes` for non-tty stdin (or `--dry-run`); refuses with `USAGE` (2) otherwise.

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

# Machine-readable config state
uv run aa_auto_sdr --config-status [--config-json]

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
| `10` | Bad config / missing credentials                            | Abort; run `--config-status --config-json`         |
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
- `--output -` implies `--quiet` (banner/progress to stderr suppressed; errors and final result paths still print).
- On failure, **stderr** receives a JSON error envelope:
  ```json
  {"error": "Configuration error: Missing credentials", "error_type": "ConfigError"}
  ```
- `--run-summary-json PATH` writes a structured run summary to file or stdout (`-`).
- **Mutex:** `--run-summary-json -` + `--output -` exits `OUTPUT` (15) before any work. `--agent-mode` applies the implicit `--output -`, so explicit `--run-summary-json -` triggers this.
- `--explain-exit-code CODE` writes the explanation to stdout. With `--run-summary-json -`, the explanation moves to stderr and run-summary JSON to stdout, keeping streams independently parseable.

---

## File Conventions

| Artifact      | Location                          | Override flag                          |
|---------------|-----------------------------------|----------------------------------------|
| SDR reports   | Current directory (default)       | `--output-dir PATH`                    |
| Snapshots     | `./snapshots/`                    | `--snapshot-dir DIR`                   |
| Log output    | `logs/` (per-run rotating files, 10 MB / 5 backups) | `--log-level`, `--log-format {text,json}`, `--quiet` |
| Profiles      | `~/.aa/orgs/<name>/`              | `--profile NAME`, `AA_PROFILE` env     |

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
uv run aa_auto_sdr --config-status --config-json         # machine-readable config state
```

### Command-Family Applicability

| Command Family            | `--agent-mode` | Notes |
|---------------------------|----------------|-------|
| Single SDR                | Limited        | Preset applies for `--log-format json`; `--output -` is suppressed (no stdout-capable format); artifacts written under `--output-dir`. |
| Batch SDR                 | Limited        | Same as Single SDR; one artifact set per RSID. |
| Discovery / Inspection    | ✅              | JSON or CSV on stdout; prefer exact RSIDs for unattended inspection. |
| Diff Family               | ✅              | JSON on stdout for `--diff`. PR-comment renderer (`--format pr-comment`) is file-only. |
| Stats                     | ✅              | JSON on stdout (`--format json`). |
| Validation / Preflight    | Partial        | Use `--config-status --config-json` for JSON state. `--validate-config` remains exit-code driven. |
| Fast-Path Flags           | Partial        | `--version`, `--exit-codes`, `--explain-exit-code`, `--completion {bash,zsh,fish}` tolerate `--agent-mode` but the preset is not applied before early exit. |
| Snapshots (list / prune)  | Partial        | `--list-snapshots --format json --output -` supported. `--prune-snapshots` requires `--yes` for non-tty stdin (or `--dry-run`); refuses with `USAGE` (2) otherwise. |

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
