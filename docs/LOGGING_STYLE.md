# aa_auto_sdr Logging Style Guide

This document is the binding contract for `logger.*(...)` call sites in `aa_auto_sdr`. Every maintainer adding instrumentation must conform to the rules here. Tests in `tests/core/` (particularly `test_logging_vocabulary.py` and `test_logging_info_budget.py`) enforce the vocabulary and discipline; the prose below is the reference those tests anchor to.

For the user-facing view of the same system (how to read logs, redaction, log file naming), see [`LOGGING.md`](LOGGING.md).

## Levels

| Level | Used for | Frequency budget |
|---|---|---|
| `CRITICAL` | Process-aborting failures: auth bootstrap fails, log-dir unwritable AND console also unwritable. | ≤2 sites total across the codebase. |
| `ERROR` | An operation failed and we are returning a non-zero exit code or surfacing the failure to the caller. Always paired with an `error_class` extra. | One per command path that can fail. |
| `WARNING` | A degradation that doesn't fail the run: best-effort log-dir fallback fired, snapshot-retention prune skipped a corrupt file, redaction sentinel fired. | Sparingly. |
| `INFO` | Run-lifecycle milestones a customer-shared log must answer: *what mode, which RSID, which component, what counts, how long, where did files land.* | See "Frequency budget" below. |
| `DEBUG` | Per-item progress, retry decisions, cache hits, parameter shapes, request/response sizes, profile resolution details. | Unbounded, only emitted when the user asks for it. |

## Structured-fields vocabulary

Every record that touches one of these concepts MUST pass it via `extra={...}` even if the same value is also interpolated into the message text. The vocabulary meta-test enforces presence on the events listed in [Canonical event names](#canonical-event-names).

| Field | Type | When |
|---|---|---|
| `rsid` | str | Any record scoped to a specific report suite. |
| `component_type` | str — `dimension`/`metric`/`segment`/`calculated_metric`/`virtual_report_suite`/`classification` | Per-component fetch records emitted from `api/fetch.py`. |
| `count` | int | Any record reporting a quantity (items fetched, files written, RSIDs in batch, components saved, files pruned). |
| `duration_ms` | int | Any record reporting an operation's elapsed time. |
| `output_path` | str | Records that announce a file written (final results, snapshot saves). |
| `format` | str — `excel`/`excel-template`/`csv`/`json`/`html`/`markdown` | Output-write records emitted from `output/writers/*`. |
| `snapshot_id` | str | Snapshot save/load/diff records. |
| `batch_id` | str | All batch-mode records. |
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
| `command` | str — dispatch attribute name | Emitted on `command_start` / `command_complete` un-prefixed records from `cli/commands/*`. Values match dispatch attribute names (e.g., `generate`, `batch`, `diff`, `list_metrics`). Vocabulary meta-test enforces presence of *some* `command` extra on cli/commands/*.py INFO records, not a fixed enum. |
| `creds_source` | str — `profile:<name>` / `env` / `.env` / `config.json` | Emitted on the INFO record from `core/credentials.resolve()` indicating which source matched. |
| `snapshot_spec` | str | Emitted from `snapshot/resolver.py` on resolve attempts. The user-supplied snapshot spec string. Used at DEBUG and ERROR. |
| `tool_version` | str | The running tool's version. May appear on records that need provenance (e.g. snapshot save). |
| `agent_mode` | bool | `run_start` / `run_complete` / `run_failure` records — `True` when `--agent-mode` preset was active; `False` otherwise. Lets log-aggregation queries filter by agent-driven runs without joining on `argv_summary`. |
| `expansion_level` | str — `full`/`minimal`/`exhausted`/`count_only` | VRS-fetch records (`api/fetch.py::fetch_virtual_report_suites`). Records which rung of the two-rung expansion ladder produced the result. See [VRS fetch behavior](#vrs-fetch-behavior) for emission sites. |
| `pulled` | int | `vrs_parent_filter` DEBUG record. Number of VRS rows the SDK returned before client-side parent filtering. |
| `filtered` | int | `vrs_parent_filter` DEBUG record. Number of VRS rows kept after the `parentRsid == parent_rsid` filter. |
| `dropped_no_parent` | int | `vrs_parent_filter` DEBUG record. Count of rows dropped because `parentRsid` was missing/empty. |
| `dropped_other_parent` | int | `vrs_parent_filter` DEBUG record. Count of rows dropped because `parentRsid` was set but didn't match the requested parent. |
| `worker_id` | int | Per-RSID log records on parallel runs (`--workers >= 2`). The submission-index of the RSID's owning worker (0..N-1). Sequential runs (`--workers 1` or unset) omit the field. Use to correlate per-RSID records to a worker without ambiguity; thread identity is separately exposed via `thread_name=aa-worker-N` from `ThreadPoolExecutor`'s `thread_name_prefix`. |
| `workers` | int | Batch records carrying the configured `--workers` value. |
| `cache_event` | str — `hit`/`miss`/`evict`/`expire` | DEBUG level on `ValidationCache.get` / `ValidationCache.put` operations. |
| `name_match_strategy` | str — `exact`/`insensitive`/`fuzzy` | `resolve_rsid` DEBUG records when the user specified `--name-match` explicitly. |
| `sample_size` | int | Number of RSIDs the user requested via `--sample N`. Emitted on the `batch_sampled` INFO record. |
| `sample_seed` | int \| None | RNG seed used for `--sample` (None when not supplied — non-deterministic run). Emitted on the `batch_sampled` INFO record. |
| `sample_strategy` | str — `random`/`stratified` | Which sampling strategy ran. Emitted on the `batch_sampled` INFO record. |
| `count_total` | int | Pre-sample population size (the original `len(batch)` before subsetting). Paired with `count` (post-sample size) on the `batch_sampled` record. |
| `audit_naming` | bool | Quality-engine emit records — whether naming-audit ran. |
| `flag_stale` | bool | Quality-engine emit records — whether stale-component flagging ran. |
| `quality_total` | int | Total quality issues found in a run. |
| `quality_by_severity` | dict | Severity → count mapping for quality issues. |
| `severity` | str | Severity name on quality records (`CRITICAL`/`HIGH`/`MEDIUM`/`LOW`/`INFO`). |
| `verdict` | str — `pass`/`fail`/`n/a` | Quality-gate evaluation result. |
| `threshold` | str | Configured severity threshold on quality-gate records. |
| `policy_path` | str | Path of a loaded `--quality-policy` file. |
| `fail_on_quality` | bool / str | Quality-gate emit records. |
| `quality_report` | str | Quality report format key on emit records. |
| `duration` | str | Duration spec string on trending records (e.g. `30d`). |
| `start_at` | str | ISO datetime — trending window lower bound. |
| `end_at` | str | ISO datetime — trending window upper bound. |
| `snapshot_count` | int | Number of snapshots that fell within a trending window. |
| `total_changes` | int | Sum of added/removed/modified across a trending window. |
| `volatility_score` | float | Per-RSID volatility metric from `compute_trending`. |
| `cycle` | int | Watch-mode cycle index (0-based). |
| `interval` | str | Watch-mode interval spec (e.g. `1h`). |
| `watch_threshold` | int | Watch-mode `--watch-threshold` value. |
| `change_count` | int | Watch-mode per-cycle change count emitted on `change` events. |
| `emitted` | bool | Whether the watch cycle emitted a `change` event (vs. suppressed by threshold). |
| `cycles_completed` | int | Watch-loop terminal record — total cycles completed before stop. |
| `rsids` | int / list[str] | Watch-loop start record — count or list of RSIDs being watched. |

For the version each field was introduced, see [Appendix A — Event and field introductions](#appendix-a--event-and-field-introductions).

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
- Never log full credentials, full request bodies, or full response bodies. Counts and shapes only. (Redaction is the safety net, not a license.)
- `logger.exception(...)` only inside `except` blocks where the traceback adds debugging value (auth bootstrap, snapshot I/O). Otherwise `logger.error(..., extra={"error_class": type(e).__name__})`.
- Never include positional CLI arguments (RSIDs, file paths) in raw form in `argv_summary`-style fields. Pass them through their dedicated structured fields (`rsid`, `output_path`).

## Canonical event names

Records intended for assertion tests use a stable verb-noun message prefix so `caplog` can match by substring without coupling to wording. The vocabulary meta-test enforces extras presence on every canonical event when its substring appears at the start of a message (token-boundary aware).

### Lifecycle (7)

- `run_start` — top-level invocation begins
- `run_complete` — top-level invocation ends successfully
- `rsid_start` — per-RSID processing begins (batch context)
- `rsid_complete` — per-RSID processing ends successfully
- `component_fetch` — single component-type fetch from AA API
- `output_write` — single output file written
- `snapshot_save` — snapshot persisted to disk

### Failure (3)

- `auth_failure` — credentials bootstrap failed
- `rsid_failure` — per-RSID processing failed (batch with `continue_on_error=True`)
- `run_failure` — top-level exception bubbled past command dispatch

### Resilience (3)

- `retry_attempt` — DEBUG. Emitted by `_log_retry_attempt` in `api/fetch.py` on every retry of a wrapped SDK call. Carries `retry_attempt` (1-indexed retry count) and `error_class`, plus `rsid` and `component_type` when the wrapping call site supplies them. `max_attempts` and `delay_s` ride along the message string for human readability without being formally indexed.
- `vrs_expansion_fallback` — WARNING. `api/fetch.py::fetch_virtual_report_suites`. Fires when the full-expansion VRS call (`extended_info=True`) exhausts the retry budget and the minimal-expansion fallback rung (`extended_info=False`) is attempted. Carries `rsid`, `component_type=virtual_report_suite`, `expansion_level=minimal`, and `error_class` (the class name of the full-rung failure that triggered the fallback).
- `vrs_parent_filter` — DEBUG. `api/fetch.py::fetch_virtual_report_suites`. Fires only when the client-side `parentRsid == parent_rsid` filter drops at least one row from the SDK response. Carries `rsid`, `pulled`, `filtered`, `dropped_no_parent`, `dropped_other_parent`.

### Batch sampling (1)

- `batch_sampled` — INFO. `pipeline/batch.py::run_batch`. Fires once per `--batch` invocation that actually applies sampling (`--sample N` where `N < len(batch)`). No-op sampling (`N >= len(batch)`) suppresses the record. Carries `count` (post-sample size, what actually runs), `count_total` (pre-sample size), `sample_size` (the user-requested N), `sample_seed` (int or None), and `sample_strategy` (`random` or `stratified`).

### Quality severity engine (3)

- `quality_audit_complete` — INFO. `sdr/quality.py::run_audits`. Fires once per audit run, regardless of whether `--fail-on-quality` was set. Carries `rsid`, `quality_total` (number of issues found) and `quality_by_severity` (dict mapping severity name to count).
- `quality_gate_evaluated` — INFO. `sdr/quality.py::run_audits`. Fires only when `--fail-on-quality` was passed. Carries `rsid`, `threshold` (the configured severity name) and `verdict` (`pass`, `fail`, or `n/a`).
- `quality_auto_enabled` — INFO. `cli/main.py::_dispatch`. Fires when the user passes `--quality-report` or `--fail-on-quality` without explicit `--audit-naming` / `--flag-stale`; auto-enables both. Carries `audit_naming` (bool) and `flag_stale` (bool).
- `quality_policy_loaded` — INFO. `sdr/quality_policy.py`. Carries `policy_path`.

### Drift / trending windows (2)

- `trending_window_resolved` — INFO. `cli/commands/trending.py::run`. Fires once per `--trending-window` invocation after the duration string is parsed. Carries `duration` (the spec string e.g. `30d`), `start_at` (ISO datetime), `end_at` (ISO datetime).
- `trending_compute_complete` — INFO. `snapshot/trending.py::compute_trending`. Fires once per RSID after compute_trending returns. Carries `rsid`, `snapshot_count`, `total_changes`, `volatility_score`.

### Watch / scheduled (3)

- `watch_loop_start` — INFO. `cli/commands/watch.py::run`. Fires once at watch dispatch entry. Carries `rsids` (count), `interval` (str), `watch_threshold`.
- `watch_cycle_complete` — INFO. `cli/commands/watch.py::_LoggingEmitter.emit`. Fires once per emitted `change` event on stdout (baseline / error events are observable via their stdout NDJSON and do not double-log). Carries `cycle`, `rsid`, `change_count`, `emitted`.
- `watch_loop_stop` — INFO. `cli/commands/watch.py::run`. Fires once at loop termination (SIGINT/SIGTERM, max_cycles, or fatal). Carries `reason` (sigint|max_cycles|fatal), `cycles_completed`.

### Git integration (v1.15.0)

| Event                  | When                                                  | Extra keys                                           |
|------------------------|-------------------------------------------------------|------------------------------------------------------|
| `git_init_repo`        | After lazy auto-init creates `.git/` + initial commit | `path`, `initial_commit`                             |
| `git_commit_complete`  | After a successful commit (and optional push)         | `rsid`, `commit_sha`, `pushed`, `duration_ms`        |
| `git_op_failed`        | On any git op failure (init / commit / push)          | `rsid`, `op` (init\|commit\|push), `error_class`, `duration_ms` |

## De-dup rule

`run_start` and `run_complete` fire **once per invocation**, from `cli/main.run` (the top frame). Sub-frames (e.g. `pipeline/batch.run_batch`) emit only their own scope-specific events (`rsid_start`, `rsid_complete`, `rsid_failure`) and never re-emit lifecycle events.

Fast-path commands (`--version`, `--help`, `--exit-codes`, `--explain-exit-code`, `--completion`) skip `setup_logging`, and therefore also skip `run_start` / `run_complete`. **`run_start` is implicitly "any non-fast-path invocation."** This is the silent-fast-path contract; it is asserted by test.

## Frequency budget at default INFO

Approximate INFO record counts per run mode at `--log-level INFO` (default). Authoritative invariants are asserted in `tests/core/test_logging_info_budget.py`; the table below is a quick reference.

| Mode | Records |
|---|---|
| Single generate, `--format excel` | 19 |
| Single generate, `--format all` (5 writers) | 23 |
| Single generate, `--output -` (pipe; no output_write) | 17 |
| Single generate, `--dry-run` (no fetches, no writes) | 11 |
| Batch generate, N RSIDs, `--format excel` | 12 + 9N |
| Diff | 9 |
| Discovery / inspect / config / profile | 9–12 |
| `--validate-config` | 10 |
| `--sample-config` | 9 |
| `--config-status` | 9 |
| `--profile-list` | 9 |
| Fast-path (`--version`, `--help`, etc.) | 0 (skips `setup_logging`) |

Each mode's total is the sum of the 5-record startup banner plus the lifecycle records (`run_start`, `command_start`, optional `creds_resolved`, `command_complete`, `run_complete`, plus optional `auth_bootstrap_ok`) plus per-component / per-write / per-command records that fire on that path. The batch budget grows linearly: per-RSID block × N RSIDs = `rsid_start` + 6 `component_fetch` + 1 `output_write` + `rsid_complete` = 9 each.

For N=10 RSIDs: **102 records.** For N=50: **462 records** — within `RotatingFileHandler` 10 MB rotation comfort zone (each NDJSON record averaging 300–600 bytes).

## VRS fetch behavior

Two fetchers in `api/fetch.py` degrade gracefully instead of failing the run: `fetch_classification_datasets` and `fetch_virtual_report_suites`. On SDK-side exception, both emit a WARNING instead of `component_fetch` INFO, return `[]`, and let the SDR build complete. The WARNING record carries `rsid`, `component_type` (`"classification"` or `"virtual_report_suite"`), and `error_class` — but not `count` or `duration_ms` (the call did not complete). All other component fetchers fail the run on exception.

### Expansion ladder

`fetch_virtual_report_suites` runs a two-rung ladder:

- **`full` rung** — `getVirtualReportSuites(extended_info=True)`. The successful `component_fetch` INFO record carries `expansion_level="full"`.
- **`minimal` rung** — fallback when the full rung exhausts its retry budget. Calls `extended_info=False` and emits a `vrs_expansion_fallback` WARNING with `expansion_level="minimal"`. If this rung succeeds, the success `component_fetch` INFO carries `expansion_level="minimal"`.
- **`exhausted`** — both rungs failed. A WARNING with `expansion_level="exhausted"` and `error_class` fires, then the fetcher returns `[]`. No `component_fetch` INFO is emitted (the function returns before the INFO emit). Log-aggregation queries that filter `component_fetch` records by `expansion_level=exhausted` will never match — query the WARNING records instead.

### VRS parent-filter visibility

After the SDK call returns, `fetch_virtual_report_suites` filters rows client-side to those whose `parentRsid` matches the requested parent. When the filter drops one or more rows, a single `vrs_parent_filter` DEBUG record fires carrying `rsid`, `pulled`, `filtered`, `dropped_no_parent`, `dropped_other_parent` — so an operator investigating "where my VRS went" can find the answer under `--log-level=DEBUG` without needing to instrument anything. No record fires on the happy path (all pulled rows kept).

### Discovery-path counterpart

`fetch_virtual_report_suite_summaries` (used by `--list-virtual-reportsuites`) does NOT graceful-degrade — silently returning `[]` would falsely suggest the org has no VRS to a user who explicitly asked for the list. Instead it normalizes any SDK-side exception to `ApiError` so the CLI's typed catch returns exit 12. A DEBUG record carrying `component_type="virtual_report_suite"` and `error_class` fires before the raise so log aggregation can correlate the failure without adding interactive console noise.

### Snapshot envelope channel

In addition to the WARNING records, `fetch_virtual_report_suites` and `fetch_classification_datasets` return `FetchOutcome[T]`, which the builder collects into `SdrDocument.fetch_status` and the snapshot writer surfaces as `degraded_components: list[str]` / `partial_components: dict[str, str]` envelope keys. Log records remain the real-time signal; the snapshot envelope is the durable signal that survives into the diff comparator.

### Request-time minimal scope (`count_only=True`)

The two graceful-degrade fetchers accept a `count_only: bool = False` kwarg. When `True`, VRS bypasses the reduced-expansion ladder and makes a single `extended_info=False` call — the `vrs_expansion_fallback` WARNING does NOT fire on this path (the fallback record is specific to ladder-driven recovery, which `count_only` deliberately skips). The `component_fetch` INFO record fires identically with `expansion_level="minimal"` describing the payload shape. On failure, a `"virtual report suites fetch failed ... expansion_level=count_only"` WARNING fires (distinct from the ladder's `"expansion_level=exhausted"`) so log analytics can distinguish the two failure paths.

Classifications' `count_only=True` is a no-op (the SDK has no expansion knob) — same call, same logs.

## Per-component fetch records

Six per-component fetchers in `api/fetch.py` each emit one `component_fetch` INFO record on success. The `component_type` extra discriminates the six fetchers — its values are `dimension`, `metric`, `segment`, `calculated_metric`, `virtual_report_suite`, and `classification`.

Required extras on every `component_fetch` INFO record: `rsid`, `component_type`, `count`, `duration_ms`.

Every SDK call in `api/fetch.py` is wrapped in either `_retry_and_normalize` (bubbling fetchers — dimensions, metrics, segments, calculated metrics, report-suite, report-suite-summaries, `resolve_rsid`) or `with_retries(_classify_transient_sdk_call(...))` inside the try/except envelope (graceful-degrade fetchers — VRS ladder, classifications, VRS-summary discovery). Each retry emits a `retry_attempt` DEBUG record.

## Output file write records

Five writers in `output/writers/*` each emit one `output_write` INFO record on a successful write. The `format` extra discriminates the five writers — its values are `excel`, `csv`, `json`, `html`, and `markdown`.

**One writer call → one record, regardless of file count.** The CSV writer produces 7 component files per invocation; it emits ONE `output_write` record with `count=7`, not 7 records. Other writers produce 1 file each and emit `count=1`.

Required extras on every `output_write` INFO record: `format`, `output_path`, `count`, `duration_ms`, `rsid`. For writers whose `write()` returns a list of N paths, `output_path` is `str(paths[0])` — abstracted so a future internal change to a writer's file shape doesn't break the contract.

## Validation cache events

`cache_event` is emitted at DEBUG level on `ValidationCache.get` / `ValidationCache.put` operations. Allowed values: `hit` / `miss` / `evict` / `expire`. The quality severity engine is the production caller; cache keys include the severity-table version so mapping changes invalidate.

## Appendix A — Event and field introductions

Most maintainers will not need this table. It exists because the vocabulary meta-test references release-anchored event sets in commit history; this is the single source of truth for "when did this enter the test contract." For everyday use, the canonical-events and vocabulary sections above describe the *current* contract — every event listed there is active, regardless of when it landed.

| Event / field | Introduced |
|---|---|
| Lifecycle 7 (`run_start`, `run_complete`, `rsid_start`, `rsid_complete`, `component_fetch`, `output_write`, `snapshot_save`) | v1.4 / v1.5 (reserved-events exemption lifted v1.5) |
| Failure 3 (`auth_failure`, `rsid_failure`, `run_failure`) | v1.4 |
| `command_start` / `command_complete` / `creds_resolved` / `rsid_resolved` | v1.5 |
| Vocabulary additions: `command`, `creds_source`, `snapshot_spec`, `tool_version` | v1.5 |
| `agent_mode` field | v1.6 |
| Resilience 3 (`retry_attempt`, `vrs_expansion_fallback`, `vrs_parent_filter`); vocabulary: `expansion_level`, `pulled`, `filtered`, `dropped_no_parent`, `dropped_other_parent` | v1.7.0 |
| `expansion_level=count_only` value | v1.7.2 |
| `degraded_components` / `partial_components` snapshot-envelope channel | v1.7.1 |
| Parallel batch fields: `worker_id`, `workers`, `cache_event` | v1.8.0 |
| Name-resolution: `name_match_strategy` | v1.9.0 |
| Batch sampling: `batch_sampled` event; `sample_size`, `sample_seed`, `sample_strategy`, `count_total` | v1.10.0 |
| Quality severity engine: `quality_audit_complete`, `quality_gate_evaluated`, `quality_auto_enabled`, `quality_policy_loaded`; vocabulary: `audit_naming`, `flag_stale`, `quality_total`, `quality_by_severity`, `severity`, `verdict`, `threshold`, `policy_path`, `fail_on_quality`, `quality_report` | v1.12.0 |
| Drift / trending: `trending_window_resolved`, `trending_compute_complete`; vocabulary: `duration`, `start_at`, `end_at`, `snapshot_count`, `total_changes`, `volatility_score` | v1.13.0 |
| Watch / scheduled: `watch_loop_start`, `watch_cycle_complete`, `watch_loop_stop`; vocabulary: `cycle`, `interval`, `watch_threshold`, `change_count`, `emitted`, `cycles_completed`, `rsids` | v1.14.0 |
| Git integration: `git_init_repo`, `git_commit_complete`, `git_op_failed`; vocabulary: `commit_sha`, `pushed`, `op`, `initial_commit` | v1.15.0 |
