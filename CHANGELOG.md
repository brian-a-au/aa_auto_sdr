# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.7.2] — 2026-05-09

Closes VRS hardening Items B + E from the audit spec. Three CLI commands
that PR #27 left as `.data` stop-gaps now fully consume the v1.7.1
`FetchOutcome` channel and surface fetch quality to the user. The same
call sites opt into a `count_only=True` fetcher mode that bypasses the
v1.7.0 reduced-expansion ladder when only counts are needed.

### Added
- `count_only: bool = False` kwarg-only parameter on `fetch_virtual_report_suites` and `fetch_classification_datasets`. For VRS, `count_only=True` calls `extended_info=False` directly, returns `FetchOutcome.healthy(stub_rows)` on success or `FetchOutcome.degraded()` on failure (no fallback to extended_info=True; no ladder). For classifications, the parameter is a documented no-op (the SDK has no expansion knob); accepted for API symmetry.
- `--describe-reportsuite` and `--stats` text/table output: count cells with non-healthy components are rendered with a trailing `*`; a footer lists each non-healthy `(rsid, component_type)` pair plus a generic disclaimer (`* (counts marked with * may be inaccurate; see logs/SDR_*.log)`).
- `--describe-reportsuite` and `--stats` JSON output: each record/row gains an optional `"fetch_status": {component_type: {status, expansion_level}}` field, populated only when at least one component is non-healthy. Plural component-type keys (`virtual_report_suites`, `classifications`).
- `--list-classification-datasets`: when classifications fetch degrades or partial-fetches, a stderr banner appears above the (possibly empty) list — one banner per non-healthy RSID for multi-RSID name lookup. Exit code unchanged (preserves pipeline UX).
- `cli/list_output.py::render_records` gains optional `footers: list[str] | None = None` parameter. Used by describe; ignored by JSON / CSV format paths.
- Helpers in `cli/list_output.py`: `_build_footer(records)` and `_annotate_cells(records)` shared between describe + stats.

### Changed
- `--describe-reportsuite` and `--stats` now call VRS + classifications fetchers with `count_only=True` internally. For typical orgs with many VRS, this skips the 15-field expansion (a 3–5× speedup on the VRS portion of the call against the v1.7.1 baseline; exact numbers vary by org size).
- `cli/commands/inspect.py::_DESCRIBE_COLS` split into `_DESCRIBE_COLS_TABULAR` (11 cols, used for table + CSV) and `_DESCRIBE_COLS_JSON` (12 cols including `fetch_status`, used for JSON only).

### Fixed
- VRS hardening Item B (latent UX gap from v1.7.1): `--describe-reportsuite` / `--stats` / `--list-classification-datasets` no longer silently render `0` (or an empty list) when Adobe's VRS or classifications endpoint flaps. The console signal makes degraded fetches visible to interactive users who wouldn't otherwise read the rotating log file.
- VRS hardening Item E (latent perf regression since v1.0): describe + stats no longer pull the 15-field VRS expansion just to compute `len()`. Single SDK round-trip per RSID per component-type.

## [1.7.1] — 2026-05-09

Closes VRS hardening Item A from the audit spec — the false-modified-diff
regression that v1.7.0's reduced-expansion ladder created when partial VRS
data lands in snapshots. Same plumbing closes the latent classifications
gap from v1.0 at zero marginal cost.

### Added
- `FetchOutcome[T]` boundary type at `api/models.py` carrying `(data, status, expansion_level)`. Status enum: `"healthy"` / `"partial"` / `"degraded"`. Used internally to plumb fetch quality from `api/fetch.py` through `sdr/builder.py` into the snapshot envelope.
- Snapshot envelope schema bumped to `aa-sdr-snapshot/v2`. Adds `degraded_components: list[str]` and `partial_components: dict[str, str]` top-level keys (always present, possibly empty `[]` / `{}`). Reader accepts both v1 and v2; writer emits v2.
- Diff suppression in all four renderers (console, markdown, json, pr_comment), in both detail and summary modes. When a component-type section comes from a degraded fetch on either side, or a partial fetch with mismatched expansion levels, the comparator suppresses per-row diff and text renderers emit a single annotation (`⚠ <Component> — diff suppressed (<reason>)`); summary-mode tables show `_suppressed_` markers in count cells instead of misleading integers; pr_comment top-line totals and breakdown table exclude suppressed sections; `cli/commands/diff.py::total_changes` (the `--warn-threshold` input) excludes suppressed sections so a degraded snapshot can't spuriously trip `WARN`.
- `ComponentDiff` gains `suppressed: bool` and `suppression_reason: str | None` fields. JSON diff renderer carries these automatically via `dataclasses.asdict`.

### Changed
- Internal: `fetch_virtual_report_suites` and `fetch_classification_datasets` now return `FetchOutcome[T]` instead of `list[T]`. No CLI surface change; user-facing `<RSID>.json` output is unchanged from v1.7.0.
- Internal: `snapshot/schema.py::validate_envelope` is the single source of truth for v1→v2 forward-compat — it mutates v1 envelopes in-place to default the new keys, so every loader path (`load_snapshot`, `resolver._resolve_path`, `_resolve_git`, `_resolve_rsid_at`) gets the same defaulting. v2 envelopes' existing values are not overwritten. Type checks (`list` / `dict`) run uniformly across v1 and v2.

### Fixed
- Snapshot diffs no longer report partial-VRS fetches as "modified" or "removed" rows. v1.7.0's reduced-expansion ladder made partial VRS data routine in snapshots; v1.7.1 plumbs the fetch-status signal end-to-end so the comparator can suppress these false-positive diffs.
- Latent classifications gap (since v1.0): a `fetch_classification_datasets` failure used to silently land in snapshots as an empty list, which a subsequent `--diff` reported as "every classification removed." Now emits `degraded_components: ["classifications"]` and the diff is suppressed.

## [1.7.0] — 2026-05-08

Closes Tier 2 "Retry / backoff knobs" from the feature gap doc, plus
Items C and D from the VRS hardening audit spec.

### Added

- `--max-retries N` (default 3), `--retry-base-delay SECONDS` (default 0.5),
  `--retry-max-delay SECONDS` (default 10.0) under a new "Retry" argparse
  group. Cross-flag mutex (`--retry-max-delay < --retry-base-delay`) exits
  `USAGE` (2) before any work.
- `src/aa_auto_sdr/api/resilience.py` — greenfield module exposing
  `RetryPolicy` (frozen dataclass with validation), `DEFAULT_RETRY_POLICY`,
  `is_retryable(exc)`, `with_retries(fn, *, policy, on_attempt)`. Per
  CLAUDE.md: retry-with-jitter only; no circuit breaker.
- `TransientApiError(ApiError)` typed signal in `core/exceptions.py`. Per
  the 2026-05-08 spike, aanalytics2 0.5.1 sets
  `urllib3.Retry(raise_on_status=False)` so non-2xx responses surface as
  `KeyError`/`ValueError` from the SDK indexing into stub error responses,
  not as `requests.HTTPError`. `_classify_transient_sdk_call` in
  `api/fetch.py` translates these to `TransientApiError` so `is_retryable`
  dispatches on a typed signal.
- Every `client.handle.getX(...)` call in `api/fetch.py` is wrapped via
  either `with_retries(...)` or `_retry_and_normalize(...)`. AST meta-test
  `tests/api/test_retry_threading.py` guards against future drift.
- `_retry_and_normalize` helper at the `api/fetch.py` boundary normalizes
  non-`ApiError` exceptions to `ApiError` so the existing CLI command-level
  `except ApiError` catches translate cleanly to `ExitCode.API` (12).
  Closes a latent v1.6.1 gap where transient fetcher failures would bubble
  past the typed catches and exit 1 + traceback.
- `AaClient.retry_policy` field; `from_credentials` accepts `retry_policy=`
  kwarg. `getCompanyId` bootstrap is wrapped under the same policy.
- Three new canonical events in `LOGGING_STYLE.md`: `retry_attempt` (DEBUG),
  `vrs_expansion_fallback` (WARNING), `vrs_parent_filter` (DEBUG). Five new
  structured fields: `expansion_level`, `pulled`, `filtered`,
  `dropped_no_parent`, `dropped_other_parent`.

### Fixed

- **VRS reduced-expansion ladder (Item C from VRS hardening spec).**
  `fetch_virtual_report_suites` now falls back to `extended_info=False`
  when the full-expansion call exhausts the retry budget, returning
  partial VRS data (id / name / parent_rsid only) instead of the v1.6.1
  empty-list graceful-degrade. Approach C (2-rung ladder) confirmed by
  spike — Approach A's reduced-expansion middle rung would require ~40
  lines of SDK-bypass and is not feasible. The fallback emits a
  `vrs_expansion_fallback` WARNING carrying `expansion_level=minimal`.
  The previous "all rungs fail → return []" floor is preserved as the
  final defense.
- **`vrs_parent_filter` DEBUG record (Item D from VRS hardening spec).**
  When `fetch_virtual_report_suites` drops rows whose `parentRsid` doesn't
  match the requested RSID (or is missing), a structured DEBUG record fires
  with `pulled` / `filtered` / `dropped_no_parent` / `dropped_other_parent`.

### Documentation

- `AGENTS.md`: Output Conventions concrete retry tuning example. New
  `## VRS Reduced Expansion` subsection documents the snapshot-diff
  false-modified caveat pending v1.8.0 (VRS hardening spec Item A).
- `README.md`: retry tuning example.
- `docs/LOGGING_STYLE.md`: three new canonical events activated; expanded
  "Best-effort fetchers" section consolidates v1.7.0 resilience-layer
  narrative.
- Feature gap doc (`docs/superpowers/specs/aa-auto-sdr-feature-gap-vs-cja.md`):
  Tier 2 "Retry / backoff knobs" row struck through with `✅ v1.7.0`.
  VRS hardening spec: Items C and D struck through.

### Reliability

- No new exit codes. No new env vars. No new runtime dependencies.
- v1.6.1 graceful-degrade preserved on full ladder exhaustion (VRS returns
  `[]`, never aborts the SDR).
- v1.6.1 discovery-path `ApiError` normalization preserved unchanged
  (`--list-virtual-reportsuites` still raises clean exit 12; the ladder
  is generate-path only).

## [1.6.1] — 2026-05-08

Patch release. Fixes a hard crash when Adobe's virtual-report-suites endpoint
fails for an org.

### Fixed

- **Generate path** (`aa_auto_sdr <RSID>`):
  `fetch_virtual_report_suites` now catches any exception from the SDK call,
  logs a `WARNING` (with `rsid` / `component_type` / `error_class`), and
  returns `[]` instead of aborting the caller. Field repro: customer org
  returned HTTP 500 from `/reportsuites/virtualreportsuites` four times
  running (initial + three retries); `aanalytics2` 0.5.1 indexes
  `vrsid['content']` on the response envelope without checking for an error
  shape, raising `KeyError: 'content'`. The exception bubbled up through
  `fetch_virtual_report_suites` → `build_sdr` → CLI and killed the entire
  generate run after every other component (331 dimensions, 122 metrics,
  16 segments, 0 calculated metrics) had already fetched cleanly. Mirrors
  the long-standing best-effort pattern used for classifications. The 500
  itself is server-side and out of scope for this tool — the customer's VRS
  list will appear empty until Adobe resolves the endpoint failure, but the
  rest of the SDR now generates normally.
- **Discovery path** (`--list-virtual-reportsuites`):
  `fetch_virtual_report_suite_summaries` now normalizes any SDK-side
  exception (e.g. raw `KeyError`, `RuntimeError`) to `ApiError` so the CLI's
  existing typed-catch contract returns exit code `API` (12) with a clean
  error message instead of an unhandled-exception traceback. Discovery does
  NOT graceful-degrade like the generate path — silently returning `[]` on
  a broken endpoint would falsely suggest the org has no VRS, hiding the
  failure from a user who explicitly asked for the list.

### Tests

- `tests/api/test_fetch.py`: added
  `test_fetch_virtual_report_suites_returns_empty_on_wrapper_error`,
  `test_fetch_virtual_report_suite_summaries_raises_api_error_on_wrapper_failure`,
  and `test_fetch_virtual_report_suite_summaries_passes_through_api_error`.
  Field-shape `KeyError("content")` is the side effect for the failure tests.
- `tests/api/test_fetch_logging.py`: added
  `test_virtual_report_suites_failure_emits_warning` (generate path —
  asserts structured `rsid` / `component_type` / `error_class` fields on
  the WARNING record) and
  `test_virtual_report_suite_summaries_failure_normalizes_to_api_error`
  (discovery path — asserts `ApiError` is raised, no WARNING).

## [1.6.0] — 2026-05-07

Closes Tier 2 "Agent mode" from the feature gap doc.

### Added

- `--agent-mode` CLI preset that defaults `--format json --output - --log-format json` for options the user did not explicitly pass. Explicit user options always win. (Spec §4.1.)
- `cli/option_resolution.py` — explicit-long-option detector (recognizes `--option value` and `--option=value` forms).
- `cli/agent_output.py` — per-command-family stdout capability resolver. Generate / batch suppress the agent-mode `--output -` default (no stdout-capable format); diff / discovery / inspection / stats stream JSON or CSV on stdout under `--agent-mode`.
- Repo-root [`AGENTS.md`](AGENTS.md) — machine-readable contract for unattended / agent-driven runs. Sections covering setup, auth, command reference, exit codes, output conventions, file conventions, agent integration, and see-also.
- `agent_mode: bool` structured field on `run_start`, `run_complete`, and `run_failure` log records (NDJSON-visible under `--log-format json`). Lets log-aggregation queries filter agent-driven runs without joining on `argv_summary`. Spec §4.5 specified `run_start` only; round-1 review extended it to the other two so failure / completion records can be correlated by the same field.

### Changed

- **Argparse abbreviations of long options now reject** instead of silently expanding. Forms like `--prof myprofile` (for `--profile`), `--forma json` (for `--format`), and `--list-rs` (for `--list-reportsuites`) error with `unrecognized arguments` under v1.6.0. The change closes a correctness gap in `--agent-mode`: the explicit-option detector that backs the preset only recognizes canonical long forms, so an abbreviation that argparse silently expanded would have let the preset overwrite the user's explicit choice. Workaround for any pinned scripts: run `aa_auto_sdr --help` and replace each abbreviated flag with its canonical long form. (Set via `allow_abbrev=False` on the parser; round-2 Codex review.)
- **`--output -` and `--run-summary-json -` now consistently imply `--quiet`.** Previously v1.5 advertised this contract in `--quiet` help text but did not enforce it at the logger level — INFO records still landed on stderr alongside stdout JSON. v1.6.0 derives the effective `--quiet` from the resolved output path before `setup_logging` runs, so console INFO chatter is silenced whenever output is stdout-bound. Errors / warnings still print on stderr, the log file is unaffected (`RotatingFileHandler` level is independent), and explicit `--quiet` users see no change. (Round-2 Codex review.)

### Removed

- None.

### Reliability

- No new exit codes. No new env vars. No new runtime dependencies. Existing `--run-summary-json -` + `--output -` mutex (exit `OUTPUT` 15) preserved; `--agent-mode --run-summary-json -` triggers it before any work.

### Tests

- `tests/cli/test_option_resolution.py`, `tests/cli/test_agent_mode_preset.py`, `tests/cli/test_agent_output_resolver.py`, `tests/cli/test_agent_mode_mutex.py`, `tests/cli/test_agent_mode_logging.py`, `tests/cli/test_agent_mode_smoke.py`, `tests/docs/test_agents_md_canonical_sections.py`. ~40 new test cases.
- v1.5 INFO budget asserted unchanged by `tests/core/test_logging_info_budget.py` (`agent_mode` field added to existing `run_start` record; no new record).

## [1.5.0] — 2026-04-29

Third Tier 2 release. **Closes the Tier 2 logging gap**: completes
codebase-wide instrumentation per the binding `LOGGING_STYLE.md` contract,
activates the two reserved canonical events from v1.4, and lands three
v1.4-review carry-over fixes. After this release, the gap doc shows
Tier 2 logging as closed.

### Added

- ~89 logger calls across 22 newly-instrumented modules (codebase total post-v1.5: ~110 calls across 26 modules). Breakdown: `api/fetch.py` (13 — six `component_fetch` INFO + classifications WARNING + 4 metadata DEBUG/ERROR), all five `output/writers/*` (one `output_write` INFO each), `sdr/builder.py` (2 DEBUG), 10 `cli/commands/*` modules (50 calls = 24 entry-function lifecycle pairs + 2 print conversions), `core/credentials.py` (10 — duplicated INFO across four resolve branches), `core/profiles.py` (4), `snapshot/comparator.py` (1), `snapshot/resolver.py` (3), `snapshot/git.py` (1).
- Two canonical events activated: `component_fetch`, `output_write`. Total active canonical events: 10 (was 8).
- Five vocabulary fields activated/added: `component_type`, `format`, `command`, `creds_source`, `snapshot_spec`.
- 12 new test files / ~50 test functions / ~75 parametrized cases. New: per-component fetch logging (`tests/api/test_fetch_logging.py`), parametrized writer logging (`tests/output/test_writer_logging.py`), builder logging, command logging across 10 modules, credentials logging, profiles logging, three snapshot logging files, INFO budget assertion (`tests/core/test_logging_info_budget.py`), `exc_text` JSON parity (`tests/core/test_logging_exc_text_json.py`), `stack_info` redaction coverage (`tests/core/test_logging_stack_info_redaction.py`).
- `docs/LOGGING_STYLE.md`: vocabulary table + canonical events flips, INFO budget table refreshed for v1.5 line counts, new subsections "Per-component fetch records" and "Output file write records."
- `docs/CONFIGURATION.md`: ten-event "Reading the log file" enumeration; new "Per-RSID instrumentation (v1.5.0)" and "Reading credential resolution (v1.5.0)" subsections.

### Changed

- Three progress prints in `cli/commands/{generate,batch}.py` and one warning print in `cli/commands/batch.py` move to logger records: now persisted to log file and gated by `--quiet`. Specifically: `using credentials from: <source>` (both files), the elif/else of `using report suite: <rsid>` in generate.py (the multi-name match `'name' matches N report suites:` print is preserved), `warning: prune failed for <rs>: <exc>` in batch.py, and one `warning: classifications fetch failed (...)` from `api/fetch.py`. **No user-facing result prints (`wrote: <path>`, batch summary banner, multi-name match line, `DRY RUN ...`) are converted.**
- `tests/core/test_logging_redaction_regression.py`: migrated from manual `try/finally` teardown to autouse-fixture pattern matching sibling v1.4 logging test files (v1.4 review carry-over #2). Behavior unchanged.
- `tests/core/test_logging_vocabulary.py`: dropped v1.4 reserved-events exemption; expanded module enumeration from 4 files to 26; extended keyword-to-extras map with v1.5 vocabulary additions.

### Fixed

- `core/logging.JSONFormatter.format` now surfaces `record.exc_text` in NDJSON output when truthy. v1.4's `SensitiveDataFilter` already pre-formats and redacts the traceback; v1.4 excluded it via the reserved-fields filter, leaving JSON consumers (Splunk/ELK/Datadog) without traceback parity. v1.5 surfaces it (already-redacted, safe to emit). Pre-existing v1.3 behavior; not a regression. Closes v1.4 review carry-over #1. **Forward-compatibility-only:** no current call site uses `logger.exception` per v1.4 style guide §6.3 (which prefers `logger.error(..., extra={"error_class": ...})`), so the fix has no immediate effect on any v1.5 record. It activates the moment a future module uses `logger.exception` with `--log-format=json`.

### Notes

- `LOG_LEVEL` env var, `--log-level`, `--log-format`, `--quiet` from v1.3 continue to control the new records.
- `worker_id` and `cache_event` vocabulary fields stay reserved; they activate when parallel batch workers and validation cache ship as separate Tier 2 releases.
- INFO budget at default level grows: single-RSID `--format excel` = 19 lines (was 8–12 in v1.4), batch ≈ 12 + 9N (was 9 + 2N). Justified by the v1.5 success criterion that customer-shared logs answer "for each RSID processed: which component types were fetched and how many" without re-running the tool. RotatingFileHandler defaults (10 MB / 5 backups) handle even N=200 batch runs comfortably.
- Tier 2 logging is **closed.** The next picks are parallel batch workers (recommended first), retry/backoff CLI knobs, validation cache, agent mode, sampling, memory caps, naming audits, field-level shaping. Each ships separately.
- No new exit codes; no new runtime dependencies; no breaking change to CLI surface.

## [1.4.0] — 2026-04-28

Second Tier 2 release. Wires the v1.3 logging framework into the four
modules where customer-shared log triage starts. Lands the binding
`docs/LOGGING_STYLE.md` so future instrumentation passes have a contract.

### Added

- `docs/LOGGING_STYLE.md` — binding style guide. Levels table, structured-
  fields vocabulary, ten canonical event names (eight active in v1.4, two
  reserved for v1.5), message-style rules, de-dup rule.
- 21 `logger.*(...)` call sites across `api/client.py` (5), `cli/main.py`
  (4), `pipeline/batch.py` (4), `snapshot/store.py` (8).
- Eight v1.4-active canonical events: `run_start`, `run_complete`,
  `run_failure`, `rsid_start`, `rsid_complete`, `rsid_failure`,
  `auth_failure`, `snapshot_save`.
- Two reserved canonical events for v1.5: `component_fetch`, `output_write`.
- `batch_id: str` on `BatchResult` — internally generated 8-char hex,
  emitted on every `pipeline/batch.py` log record so a customer-shared
  batch log is grep-able by batch.
- 24 new tests covering per-module event emission, vocabulary drift
  (AST meta-test), NDJSON schema (golden fixture for `run_complete`), and
  redaction regression for the rendered-message, non-str ``record.msg``,
  and ``exc_info`` traceback paths at new call sites.
- `docs/CONFIGURATION.md` — "Reading the log file (v1.4.0)" subsection
  enumerating the eight active events.

### Changed

- `cli/main.run` extracts `_dispatch(ns, parser) -> int` so `run_start`,
  `run_complete`, and `run_failure` have well-defined emit points around
  a single try/except. Behavior is otherwise unchanged — every previously
  reachable `ExitCode` value is still reached on the same input.
- `snapshot/store.prune_snapshots` — per-file `OSError` on `unlink` is now
  logged at WARNING and the loop continues, instead of aborting the whole
  prune. Multi-RSID prunes no longer fail on a single corrupt/locked file.

### Fixed

- `core/logging.SensitiveDataFilter` — redaction now applies to the
  rendered `record.msg % record.args` instead of msg/args separately. The
  v1.3 surface left a leak shape where a credential lived in an arg with
  surrounding context (e.g. `"Bearer"`, `"Authorization:"`) in the format
  string, defeating per-component redaction. Existing redaction patterns
  unchanged; only the application point shifted. Caught by the v1.4
  regression guard at `tests/core/test_logging_redaction_regression.py`.
- `core/logging.SensitiveDataFilter` — also closes two adjacent v1.3 leak
  shapes: (a) non-str `record.msg` (e.g. `logger.error(some_exc)` where the
  exception's `str()` carries a token) is now coerced and redacted before
  format time; (b) `record.exc_info` tracebacks from `logger.exception(...)`
  / `exc_info=True` are pre-formatted, redacted, and stuffed into
  `record.exc_text` with `exc_info` cleared so the formatter cannot
  re-render the raw traceback. Both paths covered by regression tests.

### Notes

- `LOG_LEVEL` env var, `--log-level`, `--log-format`, `--quiet` from v1.3
  continue to control the new records.
- Reserved events (`component_fetch`, `output_write`) and reserved fields
  (`worker_id`, `cache_event`) are documented but unused in v1.4. They
  activate in v1.5 alongside `api/fetch.py` / `output/writers/*`
  instrumentation and parallel-batch / validation-cache features.
- Tier 2 carryover (parallel batch workers, retry/backoff CLI knobs,
  validation cache, agent mode, sampling, memory caps, naming audits,
  field-level shaping) — defer to v1.5+.

## [1.3.0] — 2026-04-28

First Tier 2 release. Adds structured per-run logging — the only
infrastructure parity gap from `cja_auto_sdr` that subsequent Tier 2 work
(parallel workers, retry/backoff knobs, validation cache) depends on for
debuggability.

### Added

- `core/logging.py`: trimmed port of the CJA equivalent. Provides
  `setup_logging(namespace)` (single call site from `cli/main.run()`),
  `infer_run_mode(namespace)`, `SensitiveDataFilter` (redacts bearer
  tokens, `Authorization:` headers, `client_secret=` and `access_token=`
  query/body values — case-insensitive, full-value-to-EOL for
  `Authorization:`), and `JSONFormatter` (NDJSON; Splunk/ELK/Datadog
  ingest directly).
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` flag (default `INFO`,
  with `LOG_LEVEL` environment-variable fallback).
- `--log-format {text,json}` flag (default `text`).
- `--quiet` / `-q` flag. Suppresses INFO console output. Errors and final
  result paths still print. **The log file is unaffected.**
- `--color-theme {default,accessible}` flag for the diff renderer.
  `accessible` swaps green/red → blue/orange for red-green deuteranopia.
- `logs/` directory at the working directory. Per-run timestamped files:
  `SDR_Generation_<RSID>_*.log`, `SDR_Batch_Generation_*.log`,
  `SDR_Diff_*.log`, `SDR_Run_*.log` (catch-all). `RotatingFileHandler`
  at 10 MB / 5 backups. Best-effort: a `mkdir` failure (PermissionError
  or OSError) falls back to console-only with a stderr warning.
- Five-record INFO startup banner per run (log file path, version,
  Python+platform, dependency versions, run mode/level/format) — always
  emitted to file regardless of `--quiet`.
- Meta-test (`tests/meta/test_no_direct_logging_outside_core.py`)
  enforcing that only `core/logging.py` instantiates handlers / calls
  `basicConfig` / `dictConfig` / `fileConfig`. Other modules use
  `logging.getLogger(__name__)` only.
- ~50 new tests covering run-mode inference (11 modes), file-handler
  wiring, mkdir fallback, redaction (4 patterns + case-insensitive +
  Basic/Digest non-Bearer schemes + setup_logging integration),
  NDJSON schema, --quiet semantics, palette switch.

### Changed

- New `setup_logging()`-emitted banner / progress records go to **stderr**
  (so `aa_auto_sdr <RSID> --output -` keeps stdout clean for piping).
  Existing command stdout/stderr behavior is unchanged: final result
  prints (file paths, `--show-config` output, list-reportsuites tables)
  still go to stdout exactly as before.
- `core/colors.py` learns a `set_theme()` switch consulted by `success()`
  and `error()`. `bold()` and `warn()` are theme-agnostic.

### Notes

- `logs/` is git-ignored.
- Tier 2 carryover (parallel batch workers, retry/backoff CLI knobs,
  validation cache, agent mode, sampling, memory caps, naming audits,
  field-level shaping) — defer to v1.4+.
- No exit-code changes. No new policy.

## [1.2.3] — 2026-04-28

Cosmetic alignment release. Brings two internal SCOPES strings — the
`--sample-config` template and the `--explain-exit-code 11` AUTH block —
into line with the no-space comma-separated form declared canonical in
`docs/CONFIGURATION.md` and used by every example in README / QUICKSTART /
CONFIGURATION since #15. No new flags, no new exit codes, no behavior
change. Existing config files using the comma-with-space form continue to
authenticate unchanged (the `aanalytics2` SDK normalizes whitespace before
requesting tokens).

### Changed

- `--sample-config` template emits
  `"scopes": "openid,AdobeID,additional_info.projectedProductContext"`
  (no spaces) — matches the user-facing examples a reader sees in the
  docs.
- `ExitCode.AUTH` explanation (`--explain-exit-code 11`) lists the
  verified-minimum SCOPES as `openid,AdobeID,additional_info.projectedProductContext`
  (no spaces).
- `CLAUDE.md` verified-minimum SCOPES reference switched to the no-space
  canonical form, with a note pointing at `docs/CONFIGURATION.md` as the
  source of truth for the format.

## [1.2.2] — 2026-04-27

Cleanup release. Retires the dead `SANDBOX` config field (collected by
`--profile-add` / `SANDBOX` env var / `config.json` but never forwarded
to `aanalytics2.configure()` — confirmed dead by the post-#12 review
trail). Aligns two internal SCOPES defaults with the comma-separated
form used in every user-facing doc example.

### Changed

- `Credentials` dataclass loses its `sandbox` field. `_from_dict` and
  `_from_env` no longer read `sandbox` / `SANDBOX`. Pre-existing
  `config.json` and `~/.aa/orgs/<name>/config.json` files containing
  `"sandbox": null` (or any value) continue to load — the loader
  silently ignores unknown keys (regression-tested via
  `test_legacy_sandbox_key_in_config_is_ignored`).
- `--profile-add` no longer prompts for a SANDBOX value. The written
  profile JSON contains the four required keys only.
- `--show-config`, `--config-status`, and `--profile-show` no longer
  emit a `sandbox:` line.
- `--sample-config` template emits `{org_id, client_id, secret, scopes}`
  only; the `scopes` default switches from space-separated to
  comma-separated (matches every example in README / QUICKSTART /
  CONFIGURATION and the `aanalytics2.importConfigFile` path).
- `ExitCode.AUTH` explanation (`--explain-exit-code 11`) lists the
  verified-minimum SCOPES as `openid, AdobeID, additional_info.projectedProductContext`
  (comma-separated, matching the user-facing examples).
  *Superseded by 1.2.3 — the no-space form `openid,AdobeID,additional_info.projectedProductContext`
  is the canonical form going forward.*

### Removed

- `SANDBOX` env var is no longer read.
- `"sandbox": null` removed from `config.json.example` and from the
  `docs/CONFIGURATION.md` Option-3 JSON example.
- `tests/core/test_credentials_resolve.py::test_sandbox_propagates_from_env`
  deleted (the env var is no longer plumbed).

### Docs

- `docs/CONFIGURATION.md`: heading `## Multi-org / sandbox setups`
  renamed to `## Multi-org setups`; `--show-config` diagnostics line
  no longer mentions "the sandbox value".
- `docs/superpowers/specs/aa-auto-sdr-feature-gap-vs-cja.md`: rolling
  tracker bumped to v1.2.2.

## [1.2.1] — 2026-04-27

Polish release closing all seven Minor (M-1 … M-7) findings from the
independent v1.2 code review.

### Added

- `--show-timings` reactivated — emits a per-stage timings block (auth,
  resolve, build, write, snapshot) to stderr at end of run for both
  `<RSID>` and `--batch` flows. (M-7)
- `--run-summary-json PATH` reactivated — emits a structured JSON
  summary of the run (per-RSID outcomes, durations, optional timings)
  to a file or stdout (`-`). (M-7)
- `api.fetch.fetch_report_suite_summaries(client)` — typed wrapper
  that returns a sorted list of `ReportSuiteSummary` instances.
  Replaces the v1.0–v1.2 pattern of CLI command code calling
  `fetch._records(client.handle.getReportSuites(...))` directly. (M-1)
- `api.fetch.fetch_virtual_report_suite_summaries(client)` — equivalent
  typed wrapper for VRS list views; introduced as a Task-2 follow-up
  when the M-1 meta-test surfaced the second offender. (M-1)
- `api.models.ReportSuiteSummary` and `api.models.VirtualReportSuiteSummary`
  dataclasses — lightweight RS / VRS summaries (rsid + name [+ parent_rsid])
  for list-style CLI views. (M-1)
- Read-only meta-test extended: `tests/api/test_read_only_contract.py`
  now also fails CI if any module under `src/aa_auto_sdr/cli/commands/`
  reaches into `client.handle.<sdk-method>(...)` directly. (M-1)
- Regression tests for `$GITHUB_STEP_SUMMARY` reflecting the FULL diff
  even when `--show-only` / `--max-issues` filter the rendered output. (M-4)
- Regression test for `--diff-labels foo bar` (no `A=`/`B=` prefix) being
  accepted. (M-5)

### Changed

- `cli/commands/{stats,interactive,discovery}.py` migrated to the
  typed `fetch_report_suite_summaries` / `fetch_virtual_report_suite_summaries`
  wrappers. No user-visible behavior change. (M-1)
- `ExitCode.AUTH` explanation reworded: lists the verified-minimum
  three scopes (`openid AdobeID additional_info.projectedProductContext`)
  and frames `read_organizations` + `additional_info.job_function` as
  recommended for fuller endpoint coverage. Matches commit `4fcf155`. (M-3)
- `ExitCode.USAGE` explanation gains a bullet documenting the new
  `--prune-snapshots` non-interactive refusal scenario. (M-3 / M-6)
- `core/run_summary.py` module docstring refreshed now that
  `--run-summary-json` is wired. (M-2)
- `core/timings.py` gains `format_report(records=None)` rendering helper
  used by `--show-timings`. Supporting library only — no behavior change
  when the flag is unset.

### Breaking changes

- **`--prune-snapshots` non-interactive refusal exit code changed:
  `OK` (0) → `USAGE` (2).** v1.2.0 returned exit 0 when invoked on
  non-interactive stdin without `--yes` (printing `aborted` and silently no-op'ing).
  v1.2.1 returns exit 2 with a clearer message naming `--yes`. CI scripts
  that relied on the old exit 0 to mean "no-op success" need to either
  pass `--yes`, pipe `yes |`, or expect exit 2. (M-6)

### Technical

- No new exit codes; M-6 maps a new scenario onto existing `USAGE` (2).
- No new runtime dependencies.
- Read-only AA + API 2.0-only meta-tests continue to gate; the new
  CLI-commands meta-test joins them.
- Test count: 670 → ~700. Coverage gate (≥ 90%) preserved.

## [1.2.0] — 2026-04-27

Polish release closing all remaining Tier 1 gaps from the AA-vs-CJA review.

### Diff polish

- `--quiet-diff` suppresses unchanged trailers; show only changed sections (console + markdown).
- `--diff-labels A=… B=…` overrides Source/Target labels in renderer output.
- `--reverse-diff` swaps a and b before compare.
- `--warn-threshold N` exits 3 (`WARN`) when total changes ≥ N. **New exit code.**
- `--changes-only` drops component types with no changes from rendered output.
- `--show-only TYPES` restricts diff output to listed component types (CSV).
- `--max-issues N` caps each component's added/removed/modified list to N items in render.

### CI integration

- When `$GITHUB_STEP_SUMMARY` is set, `--diff` also appends a markdown render to that file. No flag needed; uses the full unfiltered report so CI surfaces are never trimmed.

### Discovery / UX

- `--stats [<RSID>...]` action — per-RSID component counts without full SDR build (table or json).
- `--interactive` action — pick an RSID from a numbered menu; emits chosen RSID(s) to stdout for shell composition.
- `--open` opens generated output in OS default app after writing (cross-platform; best-effort).
- `--yes` / `-y` skips confirmation prompts.

### Operational

- `--dry-run` extended to `<RSID>` and `--batch`: shows would-be output paths without writing. Auth round-trip still runs to validate credentials.
- `--prune-snapshots` (without `--dry-run`) now prompts for confirmation; `--yes` skips. Non-tty stdin (CI) refuses to prompt and aborts safely.

### Generation modifiers

- `--metrics-only` / `--dimensions-only` (mutex) — slim the SDR. Skips the API calls for excluded types (real perf win on large RSes).

### Config introspection

- `--config-status` prints the full credential resolution chain (more verbose than `--show-config`).
- `--validate-config` validates credential shape without calling Adobe (`org_id` must end `@AdobeOrg`, all required fields present).
- `--sample-config` emits a `config.json` template to stdout.

### Breaking changes

- **`--profile-import` no longer silently overwrites an existing profile.** It now exits 10 with a remediation message; pass `--profile-overwrite` to allow replacement. Users with existing scripts that overwrite need to add the flag.

### Technical

- New exit code `3` (`WARN`) for `--warn-threshold` exceeded. `--exit-codes` table now has 11 codes.
- `core/timings.py` — lightweight `Timer` context manager (library; not yet wired to a CLI flag).
- `core/run_summary.py` — `RunSummary` + `PerRsidResult` dataclasses (library; not yet wired to a CLI flag).
- `core/_open.py` and `core/_confirm.py` — small platform-aware helpers.
- `output/diff_renderers/_filters.py` — pure post-compare filter (changes_only, show_only, max_issues). Keeps the canonical `DiffReport` intact for downstream JSON consumers.
- `sdr/builder.py::ComponentFilter` — selects which component types `build_sdr` fetches. Pure dataclass; default = all True.
- No new runtime dependencies.
- Read-only AA + API 2.0-only meta-tests continue to gate.
- Test count: 558 → 670+ (~110 new).

## [1.1.0] — 2026-04-26

The first feature release after v1.0.0. Closes the three highest-ROI gaps from the AA-vs-CJA feature gap review, plus a CLI ergonomics upgrade.

### Generation ergonomics

- **Auto-batch:** passing 2+ identifiers on the command line now routes to batch mode automatically — `aa_auto_sdr rs1 rs2 rs3` works without `--batch`.
- **Mixed RSIDs and names:** RSIDs and case-insensitive names can be combined in one invocation — `aa_auto_sdr dgeo1xxpnwcidadobestore "Adobe Store" demo.prod`.
- `--batch` flag is preserved for backward compatibility; mixing it with positional RSIDs returns exit 2 with a clear error.

### Snapshot lifecycle

- `--auto-snapshot` saves a snapshot per RSID on `<RSID>` and `--batch <RSIDs...>` runs (requires `--profile`). Collapses with `--snapshot` to a single save when both are set.
- `--auto-prune` applies retention policy after auto-save.
- `--keep-last N` and `--keep-since <int><h|d|w>` retention rules (mutually exclusive — pick one).
- `--list-snapshots [<RSID>]` action — table or json output (requires `--profile`).
- `--prune-snapshots [<RSID>]` action — applies policy and deletes; supports `--dry-run`.

### Diff UX

- `--side-by-side` renders modified-component fields with before/after columns (console; markdown's existing layout already provides Before/After columns).
- `--summary` collapses diff output to per-component-type counts.
- `--ignore-fields description,tags` skips listed fields at every nesting level during compare. Filtering happens in the comparator, so the resulting `DiffReport` is clean for piped JSON consumers.
- `--format pr-comment` — new diff renderer optimized for GitHub PR comments, with collapsible `<details>` blocks and a 60K-char length cap.

### Profile parity

- `--profile-list` lists profile names (table or json).
- `--profile-test NAME` performs a real OAuth + `getCompanyId()` round trip and prints PASS/FAIL.
- `--profile-show NAME` prints profile fields with masked client_id (no secret).
- `--profile-import NAME FILE` imports a JSON file as a profile (validates required fields).

### Technical

- No new exit codes — new failure modes map onto existing `CONFIG` (10), `AUTH` (11), `OUTPUT` (15), `SNAPSHOT` (16). `--exit-codes` table unchanged; `--explain-exit-code` text expanded.
- Snapshot filename parsing now accepts both `+HH:MM` offset and `Z` UTC suffix (matching `snapshot/schema.py`); unparseable filenames are kept rather than deleted (fail-closed safer default).
- `captured_at` field in `--list-snapshots --format json` is now canonical ISO-8601 (with colons), not the filesystem-mangled stem.
- No new runtime dependencies.
- Read-only AA enforcement and API 2.0-only meta-tests continue to gate.
- Test count: 546 (up from 446 in v1.0.0).

## [1.0.0] — 2026-04-26

The first production release.

### What's in 1.0.0

- **Generation** of Solution Design Reference (SDR) documentation for one (`aa_auto_sdr <RSID>`) or many (`--batch RSID...`) Adobe Analytics report suites. Five output formats (Excel, CSV, JSON, HTML, Markdown) plus four aliases (`all`, `reports`, `data`, `ci`).
- **Discovery & inspection** commands without generating a full SDR: `--list-reportsuites`, `--list-virtual-reportsuites`, `--describe-reportsuite`, `--list-{metrics,dimensions,segments,calculated-metrics,classification-datasets}`, with `--filter`, `--exclude`, `--sort`, `--limit`.
- **Snapshot save** (`--snapshot`) and **`--diff <a> <b>`** between any two snapshots — the "version control of SDR" capability. Tokens: bare path, `<rsid>@<ts>`, `<rsid>@latest`, `<rsid>@previous`, `git:<ref>:<path>`. Three renderers: console, JSON, Markdown.
- **Authentication** via OAuth Server-to-Server (env vars, named profile, `.env`, or `config.json` — checked in that precedence order).
- **Read-only** against Adobe Analytics, **forever**. CI-enforced via meta-test scanning `src/aa_auto_sdr/api/` for any write-shape SDK call.
- **API 2.0 only.** No legacy 1.4 paths anywhere. CI-enforced via meta-test.
- **Fast-path actions** complete in <100ms: `-V`/`--version`, `-h`/`--help`, `--exit-codes`, `--explain-exit-code <CODE>`, `--completion {bash,zsh,fish}`.
- **Machine-readable error envelope** on stderr for pipe-path failures (`--output -` / `--format json|markdown`).
- **CI** gates on Linux, macOS, and Windows: tests + 90% coverage, ruff lint + format, version-sync, wheel build + smoke-install (`release-gate.yml`).
- **Documentation** covering quickstart, CLI reference, configuration, snapshot/diff, and output formats. README mirrors the `cja_auto_sdr` structure (sister-project parity for users moving between AA and CJA).
- **`sample_outputs/`** in the repo so anyone can browse representative outputs without installing.
- **`pyproject.toml`** classifiers promoted to `Development Status :: 5 - Production/Stable`. Wheel + sdist build cleanly via `uv build`.

### Out of scope (deferred)

- **PyPI publish.** The repo is publish-ready (wheel builds, gates pass, metadata is correct), but the actual upload to pypi.org is not part of v1.0.0. Future v1.1+ may add `publish.yml` with trusted publishing.
- **`core/logging.py` structured logging.** Defer.
- **`--stats` summary command.** Dropped.
- **Quality / validation engine, drift trending, circuit breakers, API auto-tuning.** Out of scope; defer indefinitely.
- **`docs/CONFIGURATION.md` / `docs/SNAPSHOT_DIFF.md` / `docs/OUTPUT_FORMATS.md` further deepening.** First cuts shipped in 1.0.0; expansions on demand.

## [0.9.0] — 2026-04-26

### Added
- `--exit-codes`: list every exit code with a one-line meaning. Fast-path action (no pandas/aanalytics2 import).
- `--explain-exit-code <CODE>`: paragraph-form explanation including likely causes and a "What to try" remediation block. Fast-path action.
- `--completion {bash,zsh,fish}`: emit a static shell-completion script to stdout. Fast-path action; no `argcomplete` runtime dep.
- `core/exit_codes.py`: central `ExitCode` IntEnum + `ROWS` (table) + `EXPLANATIONS` (long-form). Single source of truth; nine files migrated from per-module `_EXIT_*` constants.
- Machine-readable JSON error envelope (`output/error_envelope.py`): when `--output -` or `--format json|markdown` is in effect and an error occurs, a one-line `{"error": {...}}` is written to stderr while stdout stays silent.
- Four meta-tests in `tests/meta/` enforcing CLAUDE.md architectural invariants in CI: SDK isolation, no 1.4 paths, read-only AA, exit-code completeness.
- `scripts/check_version_sync.py` validates version string across `core/version.py`, `pyproject.toml`, `CHANGELOG.md`, `README.md`.
- Three Linux GitHub Actions workflows: `tests.yml` (pytest + coverage gate), `lint.yml` (ruff check + format), `version-sync.yml`.
- User-facing docs: `docs/QUICKSTART.md` (90-second onboarding), `docs/CLI_REFERENCE.md` (full flag table).

### Changed
- **Coverage gate:** 70% → 90% in `pyproject.toml` (per spec §11). Achieved by adding ~20 error-path tests across `cli/commands/{generate,discovery,inspect}.py` and `cli/main.py` slow-path dispatch.
- **Ruff rule set** expanded from 7 to 41 rule families (CJA-equivalent profile) with per-file-ignores for legitimate CLI `print`, intentional Unicode in docstrings, and test-only assertion patterns.
- All `_EXIT_*` integer constants in `cli/`, `pipeline/` migrated to `ExitCode.X.value` references. Wire-level behavior unchanged.

### Fixed
- `generate.py` pipe-path errors (`--output -` with `--format json`) now correctly emit a JSON error envelope to stderr for ConfigError / AuthError / ApiError / ReportSuiteNotFoundError surfaces — previously these printed to stdout, violating master spec §6.2.

### Out of scope (v1.0.0)
- macOS + Windows CI matrix.
- `release-gate.yml` and `publish.yml` (PyPI trusted publishing).
- `docs/CONFIGURATION.md`, `docs/SNAPSHOT_DIFF.md`, `docs/OUTPUT_FORMATS.md`.

## [0.7.0] — 2026-04-26

### Added
- `--snapshot` flag for `aa_auto_sdr <RSID>` and `aa_auto_sdr --batch ...`. Persists the built `SdrDocument` envelope under `~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-timestamp>.json`. Requires `--profile` (snapshots are profile-scoped). The snapshot path is appended to the `wrote:` trail and contributes to the batch banner's bytes/file totals.
- `--diff <a> <b>` action: compute a structured diff between two snapshots and render it to console (default), JSON, or Markdown.
- Snapshot envelope schema `aa-sdr-snapshot/v1`: `{schema, rsid, captured_at, tool_version, components}`. Sorted keys, atomic write, git-diff-friendly. Loaders reject unknown majors and naive timestamps with `SnapshotSchemaError`.
- Resolver token grammar: bare path | `<rsid>@<timestamp>` | `<rsid>@latest` | `<rsid>@previous` | `git:<ref>:<path>` (explicit `git show` syntax — no bare-ref defaulting).
- Comparator with identity-by-ID and §5.1 value normalization (whitespace strip, `None`/NaN/`""` equivalence, order-insensitive `tags`/`categories`) — adopted from `cja_auto_sdr/diff/comparator.py`.
- Three pure diff renderers: `output/diff_renderers/{console,json,markdown}.py`. Console respects `core/colors._enabled()` (auto-disabled for non-TTY/`NO_COLOR=1`); markdown uses GFM tables and escapes pipe characters; JSON is sorted-key + stable.
- `core/colors.warn()` yellow helper (used by the console diff renderer for `~ modified` rows and RSID-mismatch warnings).
- New exit code `16 SnapshotError` (resolve / schema / git failure).

### Behavior notes
- `--snapshot` + `--output -` works: snapshot save is an out-of-band side effect of generation, independent of the rendered output.
- `--diff --format console --output -` is rejected (exit 15); use `--format json` or `markdown` for pipes.
- The master design spec §6 originally listed exit code 14 for "Snapshot error", but v0.5 took 14 for `PARTIAL_SUCCESS`. v0.7 claims 16 instead.

### Out of scope (planned for later milestones)
- Auto-snapshot (no flag), retention/pruning, bare git refs, `--snapshot-only` — v0.9+.
- `core/exit_codes.py` central enum + `--explain-exit-code` — v0.9.

## [0.5.0] — 2026-04-26

### Added
- `--batch RSID1 RSID2 ...`: sequential SDR generation across multiple report suites with continue-on-error. Each item can be an RSID or a report-suite name (multi-match-by-name fans out within the batch). Identifiers are deduplicated after resolution.
- CJA-style end-of-run summary banner: total/successful/failed counts, success rate, total output size, total + average + throughput durations, per-RSID ✓/✗ lists with friendly names, file counts, and per-RSID duration.
- `core/colors.py`: ANSI helpers (`bold`, `success`, `error`, `status`) auto-disabled for non-TTY stdout or `NO_COLOR=1` (https://no-color.org/). Reusable by v0.7's diff renderer.
- `core/constants.py`: `BANNER_WIDTH = 60` (future home for shared CLI defaults).
- `pipeline/batch.py::run_batch`: pure orchestration — pre-resolved RSIDs in, `BatchResult` out, optional progress/failure callbacks for stdout injection. Trivially testable without `capsys`.
- New exit code: `14 PARTIAL_SUCCESS` — some batch RSIDs succeeded and some failed. All-failed batches surface the *last* failure's exit code so scripts see a real failure mode.
- `RunResult.report_suite_name` and `RunResult.duration_seconds`: friendly name (populated from the built `SdrDocument`) and per-RSID wall-clock — both surfaced in the batch summary banner.

### Behavior notes
- `--batch <RSID...> --output -` is rejected with exit 15 — piping multiple SDRs to a single stream is ambiguous.
- Continue-on-error is always on for `--batch` (no opt-in flag); aborting on first failure is what single-RSID generation already does.

### Out of scope (planned for later milestones)
- Snapshot save and `--diff` — v0.7.
- Parallel batch (`--workers N`) — deferred until real-world runtimes justify it.

## [0.3.0] — 2026-04-26

### Added
- Discovery commands: `--list-reportsuites`, `--list-virtual-reportsuites`. Show all RS / VRS visible to the org.
- Inspect commands: `--list-metrics`, `--list-dimensions`, `--list-segments`, `--list-calculated-metrics`, `--list-classification-datasets`. Each accepts an RSID or a report-suite name (matching v0.2 generate convention; multi-match-by-name produces records across all matching RSIDs with a disambiguating `rsid` column).
- `--describe-reportsuite <RSID-or-name>`: prints RS metadata + per-component counts (no full SDR built).
- `--filter STR`, `--exclude STR`, `--sort FIELD`, `--limit N` for all list/inspect commands. Case-insensitive substring match on `name`, allowlisted sort fields per command.
- `--output -` stdout piping for SDR generation (JSON only — csv/excel/html/markdown/aliases reject) and for list/inspect commands (json or csv).
- New shared CLI modules: `cli/_filters.py` (pure data pipeline) and `cli/list_output.py` (table/json/csv rendering).

### Changed
- **Internal:** `--format` no longer has a hard default at the parser level; generate command applies `excel` when omitted, list/inspect commands apply implicit-table rendering when omitted. Required because the two action types have different format allowlists.

### Out of scope (planned for later milestones)
- Batch generation (`--batch <RSID...>`) — v0.5.
- Snapshot save and `--diff` — v0.7.

## [0.2.0] — 2026-04-25

### Added
- CSV writer — multi-file output (one CSV per component type), UTF-8 with BOM, atomic writes.
- HTML writer — single self-contained file with embedded CSS, one section per component, no JavaScript.
- Markdown writer — GFM-flavored, one H2 per component, escaped pipe characters in cells.
- Format aliases (`all`, `reports`, `data`, `ci`) now resolve to working writers — `aa_auto_sdr <RSID> --format all` produces all five formats.
- Report-suite-name resolution: the positional argument now accepts either an RSID or a friendly name (case-insensitive exact match). When a name matches multiple report suites, an SDR is produced for each match (matches `cja_auto_sdr` convention). Output filenames stay keyed off the canonical RSID.
- New shared helper module `output/_helpers.py` with `stringify_cell`, `escape_pipe`, `escape_html`. Excel writer migrated to use it.

### Changed
- **Internal:** `Writer.write` returns `list[Path]` instead of `Path`. Single-file writers return a one-element list; CSV returns 7. No external behaviour change — the CLI still prints one `wrote: <path>` line per file.

### Out of scope (planned for later milestones)
- Discovery and inspection commands (`--list-reportsuites`, `--list-metrics`, etc.) — v0.3.
- Stdout piping (`--output -`) — v0.3.
- Batch generation (`--batch`) — v0.5.
- Snapshot save and `--diff` — v0.7.

## [0.1.1] — 2026-04-25

### Fixed
- `fetch_metrics` no longer passes `dataGroup=True` to `aanalytics2.getMetrics()`. The wrapper internally slices the response DataFrame to a hardcoded column list that includes `dataGroup`, but the API does not always return that column for every report suite — it raises `KeyError: "['dataGroup'] not in index"` and breaks all SDR generation. Until upstream fixes the slice, `data_group` on `Metric` will be `None` for v0.1.x. Discovered during the v0.1.0 real-API smoke test.

## [0.1.0] — 2026-04-25

### Added
- Project skeleton: `pyproject.toml`, package layout, `uv` toolchain.
- OAuth Server-to-Server authentication; four-source resolution chain (profile / env / `.env` / `config.json`).
- Profile CRUD via `--profile-add`; lookup via `--profile`.
- `--show-config` to print the resolved credential source without exposing secrets.
- Single-RSID SDR generation: dimensions, metrics, segments, calculated metrics, virtual report suites, classifications.
- JSON and Excel writers (multi-sheet, frozen header row, autofilter).
- `--version` / `--help` fast-path entry — no heavy imports.
- Pytest harness with auto-marker classification; coverage reporting.

### Out of scope (planned for later milestones)
- Remaining output formats (`csv`, `html`, `markdown`) — v0.3.
- Discovery and inspection commands — v0.3.
- Batch generation (`--batch`) — v0.5.
- Snapshot save and `--diff` — v0.7.
