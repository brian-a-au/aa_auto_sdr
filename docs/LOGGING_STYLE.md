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
| `INFO` | Run-lifecycle milestones a customer-shared log must answer: *what mode, which RSID, which component, what counts, how long, where did files land.* | Single-RSID: 8–12 lines (5 v1.3 banner + 3–7 v1.4 lifecycle). Batch: ≈ 9 + 2N lines (5 banner + run_start + auth + 2 per RSID + batch summary + run_complete). |
| `DEBUG` | Per-item progress, retry decisions, cache hits, parameter shapes, request/response sizes, profile resolution details. | Unbounded, only emitted when the user asks for it. |

## Structured-fields vocabulary

Every record that touches one of these concepts MUST pass it via
`extra={...}` even if the same value is also interpolated into the message
text. The vocabulary meta-test enforces presence on the events listed in
[Canonical event names](#canonical-event-names).

| Field | Type | When |
|---|---|---|
| `rsid` | str | Any record scoped to a specific report suite. |
| `component_type` | str — `dimension`/`metric`/`segment`/`calculated_metric`/`virtual_report_suite`/`classification` | Per-component fetch records. **Reserved in vocabulary; first use lands in v1.5 with `api/fetch.py` instrumentation.** |
| `count` | int | Any record reporting a quantity (items fetched, files written, RSIDs in batch, components saved, files pruned). |
| `duration_ms` | int | Any record reporting an operation's elapsed time. |
| `output_path` | str | Records that announce a file written (final results, snapshot saves). |
| `format` | str — `excel`/`csv`/`json`/`html`/`markdown` | Output-write records. **Reserved in vocabulary; first use lands in v1.5 with `output/writers/*` instrumentation.** |
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

**Reserved fields (do not use yet, will activate when their underlying feature lands):**

- `worker_id` — parallel batch workers (v1.5+).
- `cache_event` — validation cache (v1.5+).

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
canonical events:

Of these ten, **eight fire in v1.4** and **two are reserved for v1.5**
(marked).

**Lifecycle (7):**

- `run_start` — top-level invocation begins
- `run_complete` — top-level invocation ends successfully
- `rsid_start` — per-RSID processing begins (batch context)
- `rsid_complete` — per-RSID processing ends successfully
- `component_fetch` — single component-type fetch from AA API. **Reserved — first use in v1.5.**
- `output_write` — single output file written. **Reserved — first use in v1.5.**
- `snapshot_save` — snapshot persisted to disk

**Failure (3):**

- `auth_failure` — credentials bootstrap failed
- `rsid_failure` — per-RSID processing failed (batch with `continue_on_error=True`)
- `run_failure` — top-level exception bubbled past command dispatch

**Vocabulary meta-test treatment of reserved events.** The vocabulary
meta-test does **not** require `component_fetch` or `output_write` to
appear in v1.4 — it only verifies that *if* a v1.4 call site uses one of
those substrings in its message, the matching extras are present.
Reserved events that go unused in v1.4 are not a failure. This lets the
vocabulary land in v1.4 without forcing premature instrumentation.

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
