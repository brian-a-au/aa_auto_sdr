# aa_auto_sdr Logging Style Guide

This document is the binding contract for `logger.*(...)` call sites in
`aa_auto_sdr` v1.4 and all future call sites in the codebase. Every
maintainer adding instrumentation — whether porting an existing module to
`logging.getLogger(__name__)` or wiring a brand-new feature — must conform
to the rules here. Tests in `tests/core/` enforce the vocabulary and
discipline; the prose below is the reference those tests anchor to.

## Levels

| Level | Used for | Frequency budget |
|---|---|---|
| `CRITICAL` | Process-aborting failures: auth bootstrap fails, log-dir unwritable AND console also unwritable. | ≤2 sites total across the codebase. |
| `ERROR` | An operation failed and we are returning a non-zero exit code or surfacing the failure to the caller. Always paired with an `error_class` extra. | One per command path that can fail. |
| `WARNING` | A degradation that doesn't fail the run: best-effort log-dir fallback fired, snapshot-retention prune skipped a corrupt file, redaction sentinel fired. | Sparingly. |
| `INFO` | Run-lifecycle milestones a customer-shared log must answer: *what mode, which RSID, which component, what counts, how long, where did files land.* | Single, `--format excel`: 19 records. Single, `--format all`: 23 records. Batch, N RSIDs, `--format excel`: ≈12 + 9N records. Diff: 9 records. Discovery / inspect / config: 9–12 records. See "Frequency budget at default INFO (post-v1.5)" below for derivations. |
| `DEBUG` | Per-item progress, retry decisions, cache hits, parameter shapes, request/response sizes, profile resolution details. | Unbounded, only emitted when the user asks for it. |

## Structured-fields vocabulary

Every record that touches one of these concepts MUST pass it via
`extra={...}` even if the same value is also interpolated into the message
text. The vocabulary meta-test enforces presence on the events listed in
[Canonical event names](#canonical-event-names).

| Field | Type | When |
|---|---|---|
| `rsid` | str | Any record scoped to a specific report suite. |
| `component_type` | str — `dimension`/`metric`/`segment`/`calculated_metric`/`virtual_report_suite`/`classification` | Per-component fetch records emitted from `api/fetch.py`. |
| `count` | int | Any record reporting a quantity (items fetched, files written, RSIDs in batch, components saved, files pruned). |
| `duration_ms` | int | Any record reporting an operation's elapsed time. |
| `output_path` | str | Records that announce a file written (final results, snapshot saves). |
| `format` | str — `excel`/`csv`/`json`/`html`/`markdown` | Output-write records emitted from `output/writers/*`. |
| `snapshot_id` | str | Snapshot save/load/diff records. |
| `batch_id` | str | All batch-mode records (replaces CJA's `[batch_id]` message-text prefix). |
| `error_class` | str (exception class name) | Every `ERROR` and `CRITICAL` record. |
| `retry_attempt` | int | Retry/backoff records (DEBUG). |
| `run_mode` | str — `single`/`batch`/`diff`/`config`/`discovery`/`inspect`/etc. | `run_start` records — derived from `infer_run_mode(ns)`. |
| `argv_summary` | list[str] | `run_start` records — flag names only (anything starting with `-`); never positional values like RSIDs or file paths. |
| `exit_code` | int | `run_complete`, `run_failure`, `rsid_failure` — the exit code being returned/escalated. |
| `count_failed` | int | Batch summary records — count of RSIDs that failed (paired with `count` for successes). |
| `company_id` | str | `api/client.py` bootstrap-success record — the resolved AA `globalCompanyId`. |
| `company_id_source` | str — `explicit`/`first_of_n` | `api/client.py` bootstrap-success record — provenance of the chosen company id. |
| `client_id_prefix` | str (8 chars) | `api/client.py` post-configure DEBUG record — first 8 chars of the OAuth client id; full client id is never logged. |
| `reason` | str — discriminator | `auth_failure` records — short stable reason code (`no_companies` / `missing_global_company_id`). |
| `command` | str — dispatch attribute name | Emitted on `command_start` / `command_complete` un-prefixed records from `cli/commands/*`. Values match dispatch attribute names (e.g., `generate`, `batch`, `diff`, `list_metrics`, etc.). Vocabulary meta-test enforces presence of *some* `command` extra on cli/commands/*.py INFO records, not a fixed enum. |
| `creds_source` | str — `profile:<name>` / `env` / `.env` / `config.json` | Emitted on the v1.5 INFO record from `core/credentials.resolve()` indicating which source matched. Four values: `profile:<name>` / `env` / `.env` / `config.json`. |
| `snapshot_spec` | str | Emitted from `snapshot/resolver.py` on resolve attempts. The user-supplied snapshot spec string. Used at DEBUG and ERROR. |
| `agent_mode` | bool | `run_start` / `run_complete` / `run_failure` records — `True` when `--agent-mode` preset was active; `False` otherwise. Lets log-aggregation queries filter by agent-driven runs without joining on `argv_summary`. |
| `expansion_level` | str — `full`/`minimal`/`exhausted` | VRS-fetch records (`api/fetch.py::fetch_virtual_report_suites`). Records which rung of the v1.7.0 two-rung ladder produced the result: `full` (extended_info=True succeeded), `minimal` (fell back to extended_info=False), or `exhausted` (both rungs failed; result is `[]`). Emitted on the `component_fetch` INFO record and on the `vrs_expansion_fallback` WARNING record. |
| `pulled` | int | `vrs_parent_filter` DEBUG record (`api/fetch.py::fetch_virtual_report_suites`). Number of VRS rows the SDK returned before client-side parent filtering. |
| `filtered` | int | `vrs_parent_filter` DEBUG record. Number of VRS rows kept after the `parentRsid == parent_rsid` filter. |
| `dropped_no_parent` | int | `vrs_parent_filter` DEBUG record. Count of rows dropped because `parentRsid` was missing/empty. |
| `dropped_other_parent` | int | `vrs_parent_filter` DEBUG record. Count of rows dropped because `parentRsid` was set but didn't match the requested parent. |

**Reserved fields (do not use yet, will activate when their underlying feature lands):**

`worker_id` and `cache_event` remain reserved pending parallel-batch and validation-cache features (separate Tier 2 releases).

## Message-style rules

- Format: `event_prefix key1=%s key2=%s` followed by positional args, plus `extra={...}` for the structured copy. Both views (text-grep and JSON-aggregator) get the same data:

  ```python
  logger.info(
      "rsid_start rsid=%s mode=%s",
      rsid, mode,
      extra={"rsid": rsid},
  )
  ```

- Use `%s` interpolation, never f-strings or `.format()` — standard cost-of-formatting deferral so DEBUG records cost nothing when the level is INFO.
- Never log full credentials, full request bodies, or full response bodies. Counts and shapes only. (v1.3 redaction is the safety net, not a license.)
- `logger.exception(...)` only inside `except` blocks where the traceback adds debugging value (auth bootstrap, snapshot I/O). Otherwise `logger.error(..., extra={"error_class": type(e).__name__})`.
- Never include positional CLI arguments (RSIDs, file paths) in raw form in `argv_summary`-style fields. Pass them through their dedicated structured fields (`rsid`, `output_path`).

## Canonical event names

Records intended for assertion tests use a stable verb-noun message prefix
so `caplog` can match by substring without coupling to wording. The ten
canonical events, all active in v1.5:

**Lifecycle (7):**

- `run_start` — top-level invocation begins
- `run_complete` — top-level invocation ends successfully
- `rsid_start` — per-RSID processing begins (batch context)
- `rsid_complete` — per-RSID processing ends successfully
- `component_fetch` — single component-type fetch from AA API
- `output_write` — single output file written
- `snapshot_save` — snapshot persisted to disk

**Failure (3):**

- `auth_failure` — credentials bootstrap failed
- `rsid_failure` — per-RSID processing failed (batch with `continue_on_error=True`)
- `run_failure` — top-level exception bubbled past command dispatch

**Vocabulary meta-test treatment.** All 10 canonical events are active in v1.5; the v1.4 reserved-events exemption is removed. The vocabulary meta-test enforces extras presence on every canonical event when its substring appears in a message.

## De-dup rule

`run_start` and `run_complete` fire **once per invocation**, from
`cli/main.run` (the top frame). Sub-frames (e.g. `pipeline/batch.run_batch`)
emit only their own scope-specific events (`rsid_start`, `rsid_complete`,
`rsid_failure`) and never re-emit lifecycle events.

Fast-path commands (`--version`, `--help`, `--exit-codes`,
`--explain-exit-code`, `--completion`) skip `setup_logging` per v1.3, and
therefore also skip `run_start` / `run_complete`. **`run_start` is
implicitly "any non-fast-path invocation."** This is the silent-fast-path
contract; it is asserted by test.

## Frequency budget at default INFO (post-v1.5)

Per-mode INFO line counts at `--log-level INFO` (default). Each mode's
total is the sum of the v1.3 banner (5 records, always emitted) plus the
v1.4 lifecycle records plus the v1.5 per-component / per-write / per-
command records that fire on that path.

### Single-RSID generate at `--format excel` (default)

| Source | Records |
|---|---|
| v1.3 banner | 5 |
| v1.4 `auth bootstrap ok` (api/client.py) | 1 |
| v1.4 `run_start` (cli/main.py) | 1 |
| v1.5 `command_start command=generate` (cli/commands/generate.py) | 1 |
| v1.5 `creds_resolved` (core/credentials.py) | 1 |
| v1.5 `rsid_resolved` (cli/commands/generate.py) | 1 |
| v1.5 `component_fetch` × 6 (api/fetch.py) | 6 |
| v1.5 `output_write format=excel` (output/writers/excel.py) | 1 |
| v1.5 `command_complete command=generate` (cli/commands/generate.py) | 1 |
| v1.4 `run_complete` (cli/main.py) | 1 |
| **Total** | **19** |

The `rsid_resolved` and `creds_resolved` records replace existing `print()`
calls so they are net new in the log file but not net new in the user's
terminal experience.

### Single-RSID generate at `--format all` (5 writers)

19 (above) + 4 additional `output_write` records = **23**.

### Batch generate at `--format excel`, N RSIDs

| Source | Records |
|---|---|
| v1.3 banner | 5 |
| v1.4 `auth bootstrap ok` | 1 |
| v1.4 `run_start` | 1 |
| v1.5 `command_start command=batch` | 1 |
| v1.5 `creds_resolved` | 1 |
| Per-RSID block × N: `rsid_start` + 6 `component_fetch` + 1 `output_write` + `rsid_complete` = 9 each | 9N |
| v1.4 `batch_summary` (pipeline/batch.run_batch) | 1 |
| v1.5 `command_complete command=batch` | 1 |
| v1.4 `run_complete` | 1 |
| **Total** | **12 + 9N** |

For N=3 RSIDs: **39 records.** For N=10: **102 records.** For N=50:
**462 records** — within `RotatingFileHandler` 10 MB rotation comfort
zone (each NDJSON record averaging 300–600 bytes).

### Discovery / inspect / snapshot lifecycle / profile / config / stats / interactive

| Source | Records |
|---|---|
| v1.3 banner | 5 |
| v1.4 `auth bootstrap ok` (only if the command requires auth — not for `--exit-codes`/`--completion`/`--validate-config`/`--sample-config`/`--config-status` which skip auth) | 0 or 1 |
| v1.4 `run_start` | 1 |
| v1.5 `command_start command=<cmd>` | 1 |
| v1.5 `creds_resolved` (only auth paths) | 0 or 1 |
| Command-specific INFO records (varies — usually 0–2) | 0–2 |
| v1.5 `command_complete command=<cmd>` | 1 |
| v1.4 `run_complete` | 1 |
| **Total** | **9–12** |

### Diff

| Source | Records |
|---|---|
| v1.3 banner | 5 |
| v1.4 `run_start run_mode=diff` | 1 |
| v1.5 `command_start command=diff` | 1 |
| v1.5 `command_complete command=diff` | 1 |
| v1.4 `run_complete` | 1 |
| **Total** | **9** |

(Diff is fast; no auth bootstrap and no per-component fetches since it
operates on snapshot files, not the live API. Snapshot resolution and
comparator work happen at DEBUG.)

### Variant paths (record-shaped differently)

Three variant paths produce shorter or differently-shaped logs by design.

#### `--output -` (pipe path, single-RSID)

Pipe-to-stdout mode in `cli/commands/generate.py` writes the SDR JSON
directly to stdout without invoking any output writer's `.write()`
method. **Therefore `output_write` does NOT fire on the pipe path.**

| Source | Records |
|---|---|
| Banner + auth + run_start + command_start + creds_resolved + rsid_resolved | 9 |
| `component_fetch` × 6 | 6 |
| `output_write` (skipped — pipe path) | 0 |
| command_complete + run_complete | 2 |
| **Total** | **17** |

#### `--dry-run` (single-RSID)

Dry-run preview-only mode skips `build_sdr` entirely (no component
fetches, no file writes). Auth and RSID resolution still happen.

| Source | Records |
|---|---|
| Banner + auth + run_start + command_start + creds_resolved + rsid_resolved | 9 |
| `component_fetch` × 0 (skipped — no build) | 0 |
| `output_write` × 0 (skipped — no writes) | 0 |
| command_complete + run_complete | 2 |
| **Total** | **11** |

#### Fast-path (`--version`, `--help`, `--exit-codes`, `--explain-exit-code`, `--completion`)

Per v1.3 / v1.4 silent-fast-path contract: `setup_logging` is NOT
called. **Zero records on disk, zero records on stderr.**

#### No-auth commands

`--validate-config`, `--sample-config`, `--config-status` and
`--profile-list`, `--profile-show`, `--profile-import` do not call
`AaClient.from_credentials`. The auth-bootstrap INFO record from
`api/client.py` does NOT fire on these paths.

| Mode | Banner | run_start | command_start | creds_resolved | auth | command_complete | run_complete | Total |
|---|---|---|---|---|---|---|---|---|
| `--validate-config` | 5 | 1 | 1 | 1 | 0 | 1 | 1 | 10 |
| `--sample-config` | 5 | 1 | 1 | 0 | 0 | 1 | 1 | 9 |
| `--show-config` | 5 | 1 | 1 | 1 | 0 | 1 | 1 | 10 |
| `--config-status` | 5 | 1 | 1 | 0 (uses `resolution_chain`, not `resolve`) | 0 | 1 | 1 | 9 |
| `--profile-list` | 5 | 1 | 1 | 0 | 0 | 1 | 1 | 9 |

## Per-component fetch records

Six per-component fetchers in `api/fetch.py` each emit one `component_fetch`
INFO record on success. The `component_type` extra discriminates the six
fetchers — its values are `dimension`, `metric`, `segment`,
`calculated_metric`, `virtual_report_suite`, and `classification`.

Required extras on every `component_fetch` INFO record: `rsid`,
`component_type`, `count`, `duration_ms`.

**Best-effort fetchers.** Two fetchers degrade gracefully instead of
failing the run: `fetch_classification_datasets` (since v1.0) and
`fetch_virtual_report_suites` (since v1.6.1, after a customer hit
`KeyError: 'content'` from `aanalytics2` 0.5.1 when the VRS endpoint
returned HTTP 500). On SDK-side exception, both fetchers emit a
WARNING (no canonical event prefix) instead of `component_fetch` INFO,
return `[]`, and let the SDR build complete. The WARNING record carries
`rsid`, `component_type` (`"classification"` or `"virtual_report_suite"`),
and `error_class` — but not `count` or `duration_ms` (the call did not
complete). All other component fetchers fail the run on exception.

**VRS parent-filter visibility (v1.7.0, Item D).** After the SDK call
returns, `fetch_virtual_report_suites` filters VRS rows client-side to
those whose `parentRsid` matches the requested parent. When that filter
drops one or more rows, a single DEBUG record with prefix
`vrs_parent_filter` fires carrying `rsid`, `pulled`, `filtered`,
`dropped_no_parent`, and `dropped_other_parent` — so an operator
investigating "where my VRS went" can find the answer under
`--log-level=DEBUG` without needing to instrument anything. No record
fires on the happy path (all pulled rows kept).

**Discovery-path counterpart.** `fetch_virtual_report_suite_summaries`
(used by `--list-virtual-reportsuites`) does NOT graceful-degrade —
silently returning `[]` would falsely suggest the org has no VRS to a
user who explicitly asked for the list. Instead it normalizes any
SDK-side exception to `ApiError` so the CLI's typed catch returns
exit 12. A DEBUG record carrying `component_type="virtual_report_suite"`
and `error_class` fires before the raise so log aggregation can
correlate the failure without adding interactive console noise.

## Output file write records

Five writers in `output/writers/*` each emit one `output_write` INFO
record on a successful write. The `format` extra discriminates the five
writers — its values are `excel`, `csv`, `json`, `html`, and `markdown`.

**One writer call → one record, regardless of file count.** The CSV
writer produces 7 component files per invocation; it emits ONE
`output_write` record with `count=7`, not 7 records. Other writers
produce 1 file each and emit `count=1`.

Required extras on every `output_write` INFO record: `format`,
`output_path`, `count`, `duration_ms`, `rsid`. For writers whose
`write()` returns a list of N paths, `output_path` is `str(paths[0])` —
abstracted so a future internal change to a writer's file shape
doesn't break the contract.
