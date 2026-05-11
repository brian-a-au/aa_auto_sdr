# Logging

User-facing reference for `aa_auto_sdr` log output. Every non-fast-path invocation writes a per-run log file under `./logs/` (relative to the working directory). Fast-path entries (`--version`, `--help`, `--exit-codes`, `--explain-exit-code`, `--completion`) skip logging — they exit too quickly to be worth recording.

For the internal logger-call contract (canonical event names, required extras, vocabulary meta-test), see [`LOGGING_STYLE.md`](LOGGING_STYLE.md).

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` | `INFO` (or `LOG_LEVEL` env var) | Sets root logger level. |
| `--log-format {text,json}` | `text` | Output format for both console and file. `json` emits NDJSON (one JSON object per line) — Splunk / ELK / CloudWatch / Datadog ingest it directly. |
| `--quiet` / `-q` | off | Suppresses INFO-level console output (banners, progress). Errors and final result paths still print. **The log file is unaffected** — full records still land on disk. Designed for CI: `aa_auto_sdr <RSID> --quiet` gives clean stdout for piping; if a run fails, the log file has the trail. |

## Log file naming

Timestamp is UTC `YYYYMMDD_HHMMSS`. Files rotate at 10 MB / 5 backups.

| Run mode | Filename pattern |
|----------|------------------|
| single generate | `logs/SDR_Generation_<RSID>_<UTC_TS>.log` |
| batch generate | `logs/SDR_Batch_Generation_<UTC_TS>.log` |
| diff | `logs/SDR_Diff_<UTC_TS>.log` |
| everything else | `logs/SDR_Run_<UTC_TS>.log` |

`logs/` is git-ignored. Treat as ephemeral run artifacts.

## Redaction

The following patterns are scrubbed from records before they reach disk (case-insensitive):

- `Bearer <token>` → `Bearer [REDACTED]`
- `Authorization: <value>` → `Authorization: [REDACTED]` (full header value, not just the scheme)
- `client_secret=<value>` → `client_secret=[REDACTED]`
- `access_token=<value>` → `access_token=[REDACTED]`
- `extra={"client_secret": "..."}` and other known sensitive keys are also redacted in JSON output.

**Scoped to OAuth Server-to-Server.** Redaction patterns cover the credential shapes that actually appear on the OAuth S2S wire — `Bearer` headers, the `Authorization:` line, and `client_secret`/`access_token` form/query values. Patterns for `id_token`, `refresh_token`, and `jwt_token` are deliberately not included: OAuth S2S responses do not emit them, JWT auth is sunset, and `CLAUDE.md` mandates OAuth S2S as the only supported path. If a future Adobe API change adds new shapes, extend `_REDACTION_PATTERNS` in `src/aa_auto_sdr/core/logging.py`.

## Reading the log file

Beyond the startup banner, the following events are emitted at INFO/ERROR
from the core modules. See [`LOGGING_STYLE.md`](LOGGING_STYLE.md) for the
full canonical vocabulary and the binding contract.

| Event | Level | Source | Meaning |
|---|---|---|---|
| `run_start` | INFO | `cli/main.py` | Top-level invocation begins. Carries `run_mode`, `argv_summary`. |
| `run_complete` | INFO | `cli/main.py` | Top-level invocation succeeded. Carries `exit_code`, `duration_ms`. |
| `run_failure` | ERROR | `cli/main.py` | Top-level exception escaped command dispatch. Carries `exit_code`, `error_class`. |
| `rsid_start` | INFO | `pipeline/batch.py` | Per-RSID processing begins. Carries `rsid`, `batch_id`. |
| `rsid_complete` | INFO | `pipeline/batch.py` | Per-RSID processing succeeded. Carries `rsid`, `batch_id`, `duration_ms`, `count`. |
| `rsid_failure` | ERROR | `pipeline/batch.py` | Per-RSID processing failed (continue-on-error swallowed it). Carries `rsid`, `batch_id`, `exit_code`, `error_class`. |
| `auth_failure` | ERROR | `api/client.py` | Credentials bootstrap failed. Carries `error_class`, `reason`. |
| `snapshot_save` | INFO | `snapshot/store.py` | Snapshot persisted to disk. Carries `snapshot_id`, `rsid`, `output_path`, `count`, `duration_ms`. |
| `component_fetch` | INFO | `api/fetch.py` | Per-component AA fetch returned. Carries `rsid`, `component_type` (one of: dimension/metric/segment/calculated_metric/virtual_report_suite/classification), `count`, `duration_ms`. |
| `output_write` | INFO | `output/writers/*` | Output file written. Carries `format` (one of: excel/csv/json/html/markdown), `output_path`, `count` (1 for excel/json/html/markdown, 7 for csv), `duration_ms`, `rsid`. |

## Per-RSID instrumentation

Each RSID processed in a single or batch run emits **per-component fetch records** and **output write records** in the log file.

**Component fetch records** trace each AA API fetch:

```
2026-05-06 12:34:56 - aa_auto_sdr.api.fetch - INFO - component_fetch rsid=demo.prod component_type=dimension count=42 duration_ms=180
2026-05-06 12:34:57 - aa_auto_sdr.api.fetch - INFO - component_fetch rsid=demo.prod component_type=metric count=15 duration_ms=125
```

Six records per RSID, one per component type. Use these to triage where time is spent or which fetch failed:

```
grep "component_fetch" logs/SDR_*.log | wc -l   # should be 6 × N RSIDs
grep "component_fetch" logs/SDR_*.log | grep duration_ms=$(seq -s'\|' 1000 5000)   # find slow fetches
```

**Output write records** trace each format file written:

```
2026-05-06 12:35:01 - aa_auto_sdr.output.writers.excel - INFO - output_write format=excel output_path=output/demo.prod.xlsx count=1 duration_ms=820
2026-05-06 12:35:02 - aa_auto_sdr.output.writers.csv - INFO - output_write format=csv output_path=output/demo.prod_summary.csv count=7 duration_ms=140
```

CSV emits ONE record with `count=7` (the writer produces a summary file plus six per-component files); other formats emit `count=1`. To verify the run wrote everything expected:

```
grep "output_write" logs/SDR_*.log
```

## Reading credential resolution

Every non-fast-path invocation logs which credentials source resolved:

```
2026-05-06 12:34:55 - aa_auto_sdr.core.credentials - INFO - creds_resolved source=env
```

The four `creds_source` values are:

- `profile:<name>` — a named profile under `~/.aa/orgs/<name>/`
- `env` — environment variables (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`)
- `.env` — a `.env` file in the working directory
- `config.json` — a `config.json` file in the working directory

Each command also emits a lifecycle pair:

```
2026-05-06 12:34:55 - aa_auto_sdr.cli.commands.generate - INFO - command_start command=generate
[... fetches and writes ...]
2026-05-06 12:35:02 - aa_auto_sdr.cli.commands.generate - INFO - command_complete command=generate exit_code=0 duration_ms=7400
```

Use these to triage which command path was dispatched and how long the work took.

## See also

- [`CONFIGURATION.md`](CONFIGURATION.md) — credentials and profile resolution
- [`LOGGING_STYLE.md`](LOGGING_STYLE.md) — the internal logger-call contract (canonical events, required extras, vocabulary meta-test)
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — full flag reference
