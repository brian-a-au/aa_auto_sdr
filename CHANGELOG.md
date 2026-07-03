# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.21.5] — 2026-07-02

Correctness & performance patch following up v1.21.4. No new flags and no
changed defaults.

### Fixed
- Virtual-report-suite counts on `--describe-reportsuite`, `--stats`, and
  `--inventory-summary` were always zero. The count paths requested the SDK's
  reduced expansion, whose rows carry only `name` and `vrsid` — no
  `parentRsid` — so the client-side parent filter dropped every row. Count
  paths now request full expansion; the single-call, healthy/degraded
  contract is unchanged.
- The remaining NaN pollution from ragged DataFrame rows is closed for the
  fetchers that have no raw option in the SDK (dimensions, metrics, virtual
  report suites, and the report-suite listing): missing cells no longer
  surface as the literal string `"nan"` (description, type, parent, timezone,
  …) or as `True` for missing booleans (`pathable`, `segmentable`), and
  NaN-valued cells in unknown passthrough columns are dropped from `extra`
  instead of serializing as a bare `NaN` token (invalid strict JSON) in
  snapshots. Same class of bug v1.21.4 fixed for segments/calculated metrics
  via `format="raw"`; affected report suites will show a one-time snapshot
  diff as values correct.

### Changed
- The VRS reduced-expansion fallback rung is removed. With the real SDK it
  could only ever return an empty "partial" result (its rows lack
  `parentRsid`) after spending a second full retry budget — so full-rung
  exhaustion now degrades directly. This halves the VRS worst-case request
  budget (32 → 16 at defaults), retires the `vrs_expansion_fallback` log
  event and the `minimal` expansion level, and means new snapshots no longer
  populate `partial_components`. Snapshots written by earlier releases keep
  loading and diffing exactly as before.
- Report-suite and virtual-report-suite listings page at the API maximum
  (1000 per request) instead of the SDK default (100), cutting listing HTTP
  round trips ~10x for large orgs. Mirrors the v1.21.4 segments/calculated-
  metrics change.
- The Excel writer computes column widths from the already-stringified cells
  instead of re-converting every column through pandas. Output is unchanged.

## [1.21.4] — 2026-07-02

Performance & correctness patch. No new flags and no changed defaults. Faster
light-command startup, fewer redundant API calls, and one data-correctness fix.

### Fixed
- Segments and calculated metrics are now fetched with `format="raw"` instead of
  round-tripping through a pandas DataFrame. The DataFrame path filled absent
  cells of ragged rows with `NaN`, which surfaced as the literal string `"nan"`
  for missing `description` / `created` / `modified` and as `True` for missing
  booleans. Affected report suites will show a one-time snapshot diff on the next
  capture as these values correct to `null` / their true value. The snapshot
  schema (`aa-sdr-snapshot/v4`) is unchanged. Report-suite metadata fields
  (`timezone`, `currency`, `parent_rsid`) may show the same one-time
  correction, since the single-suite lookup no longer round-trips through a
  ragged full-company DataFrame.
- A deterministic `KeyError: "[...] not in index"` from the SDK's column slicing
  is now treated as permanent and fails fast, instead of being retried with the
  full budget (which re-ran the entire paginated fetch before failing the same
  way).

### Changed
- Light commands (`--diff`, `--show-config`, `--list-snapshots`,
  `--trending-window`, and the other no-network paths) no longer import
  `pandas` / `aanalytics2` / `requests` at startup, cutting ~0.3–0.4 s off their
  launch. Meta-tests guard the import boundary.
- The report-suite listing is fetched once per invocation. A single-suite lookup
  now uses the API's server-side `rsid_list` filter, and the batch / stats /
  inventory resolve loops resolve every identifier against one listing instead of
  one per identifier.
- Segments and calculated metrics page at the API maximum (1000 per request)
  instead of 500.
- CSV and HTML writers build each row's dict once instead of once per column;
  trending streams snapshots with a two-envelope window instead of loading the
  whole window into memory; the snapshot/pipe paths reuse a single serialized
  document payload. Output is unchanged.
- Minor internal tidy-ups: retention `keep_last` selection, single log-redaction
  pass, and one fewer git subprocess per commit.

## [1.21.3] — 2026-06-25

Test-coverage patch. No new flags and no change to runtime behavior. Line coverage rose from 94.3% to 99.7% and the suite grew from 2094 to 2252 tests.

### Tests
- `cli/commands/generate.py` and `cli/commands/batch.py` — the two largest remaining gaps — are now near-fully covered. New tests exercise the format/template/writer pre-flight guards, the `--template` → `excel-template` format swap, the stdout-pipe and file-write error paths, dry-run CSV and snapshot listing, the auto-prune policy branches, open-after-write, and the quality gate. Batch adds coverage for per-RSID worker error handling, the partial-success rollup, and the sampling and fail-fast branches.
- `cli/commands/interactive.py`, `discovery.py`, `stats.py`, `profiles.py`, `inventory.py`, `notion_prune.py`, `push_to_notion.py`, and `cli/list_output.py` now have explicit error-path tests: auth / API / config / generic exceptions, `EOFError` on prompt, degraded fetch-status footers, the Notion `object_not_found` and import-guard fallbacks, and the atomic-write temp-file cleanup on a failed replace.
- `cli/commands/trending.py` gains coverage for invalid-format rejection, the JSON / Markdown / console-to-file renderers, and profile-based snapshot-dir resolution.
- `pipeline/workers.py`, `pipeline/single.py`, `snapshot/git.py`, and `snapshot/store.py` are now fully covered. New tests drive the fail-fast cancel loop and the Notion watch-publish path in the parallel batch runner, and the git failure paths (git binary missing, init / add / commit non-zero returns, the `FileNotFoundError` / `TimeoutExpired` guards) via the `_run_git` / `subprocess.run` seam.
- The output layer is now fully covered: the Excel-template writer's styling and anchor branches, the CSV writer edge cases, the Notion block builders, the Notion client-guard import branches, the registry lookups, the diff console and PR-comment renderers, and the trending Markdown renderer.
- `core/logging.py`, `api/fetch.py`, `sdr/quality.py`, `sdr/quality_policy.py`, and the `cli/main.py` dispatch and `--template` validation branches gained targeted error-path and usage-path tests.

## [1.21.2] — 2026-06-25

Test-coverage patch. No new flags and no change to runtime behavior. Line coverage rose from 92.6% to 94.3% and the suite grew from 2052 to 2094 tests.

### Tests
- `cli/commands/watch.py` is now fully covered. New unit tests exercise the real-collaborator adapters (`_WallClock`, `_RealSleeper`, `_BuildSdrFetcher`, `_SnapshotStoreAdapter`, `_NotionWatchPublisher`), the `_build_real_fetcher` / `_build_notion_publisher` constructors, the signal-handler install on the non-injected path, the `--format notion` publisher build, and the fatal-exception guard around the watch loop. These are the paths the `_injected` test seam bypasses.
- `cli/commands/notion_repair.py` is now fully covered: the `NotionRegistryError` branch, the generic-exception branch, the type-conflict report on a dry run, and the type-conflict warning on apply.
- `snapshot/resolver.py` and `output/error_envelope.py` are now fully covered. Added error-path tests for a missing or unreadable snapshot file, non-JSON file contents, malformed `<rsid>@<spec>` tokens, an unknown timestamp, an unknown rsid directory, non-JSON `git:` content, and the empty-hint fallbacks for unknown and remediation-free exit codes.
- Added inspect-command error-path tests for `--list-metrics` and `--describe-reportsuite`: API errors, generic errors, and an invalid `--limit` now have explicit exit-code coverage.
- Added fast-path tests for `__main__` (`--explain-exit-code` with a missing or non-integer code, `--completion` with no shell, `--notion-print-database-schema` combined with other arguments), for `core/json_io` (temp-file cleanup when a write fails partway), and for `core/credentials` (python-dotenv absent, and an unmatched profile reported in the resolution chain).

## [1.21.1] — 2026-06-23

Bug fix for credential resolution from a `.env` file.

### Fixed
- `.env` loading now resolves credentials. A `.env` copied from `.env.example` uses the uppercase env-var keys (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`), but `_from_dotenv` passed those keys to the loader unchanged while every other source normalizes to lowercase. All four fields came back empty, so `.env` resolution silently fell through to "No credentials found." The `.env` path now lowercases keys before normalizing, mirroring how the environment-variable path maps `ORG_ID` to `org_id`. The uppercase keys in `.env.example` are the intended contract and are unchanged.

### Tests
- Added a credential-resolution test that writes a `.env` with uppercase keys and asserts it resolves with `source == ".env"`. `python-dotenv` is now in the dev dependency group so this path runs under test.

## [1.21.0] — 2026-06-21

The Notion integration gains `--notion-create-database`: a standalone mode that creates the SDR Registry database with the full canonical schema under `NOTION_PARENT_PAGE_ID` in one command — closing the last manual step in Notion setup. A database created under a page the integration already reaches inherits that access, so no separate "Share with integration" step is needed.

### Added
- `--notion-create-database` — standalone mode; creates the registry database with all `PROPERTY_SCHEMA` properties via a single `databases.create` call (`initial_data_source.properties`). Preview by default; `--yes` creates it and prints the new database id to set as `NOTION_REGISTRY_DATABASE_ID`. Requires `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID`.
- `--notion-database-title NAME` — optional title for the created database (default: `AA SDR Registry`). Requires `--notion-create-database`.
- New events: `notion_create_planned` (INFO, dry-run preview), `notion_database_created` (INFO, apply), `notion_create_existing_registry` (WARNING, a registry id is already configured), `notion_create_failed` (WARNING, the create call raised).

### Changed
- `--yes` / `-y` now also confirms `--notion-create-database`.

### Constraints
- `--notion-create-database` is a standalone mode: naming it with generation, `--batch`, `--push-to-notion`, `--diff`, `--watch`, `--notion-prune-orphans`, or `--notion-repair-database` exits `ExitCode.USAGE`. `--notion-database-title` without `--notion-create-database` exits `USAGE`.
- AA invariants untouched — the Notion path never imports `aanalytics2`; meta-tests under `tests/meta/` are unaffected.

## [1.20.1] — 2026-06-21

Efficiency, observability, and cleanup patch for the Notion integration. No new user-facing flags.

### Performance
- The resolved Notion data source is now cached per database id per run. Parallel batch and watch no longer re-fetch the database schema on every upsert.

### Added
- `notion_prune_planned` (INFO) — dry-run preview event for `--notion-prune-orphans`, reporting the count of orphaned pages found.
- `notion_repair_planned` (INFO) — dry-run preview event for `--notion-repair-database`, reporting the count of properties to add and type conflicts found.
- Restored the `Page` and `Quality Verdict` hints in `--notion-print-database-schema` output.

### Docs
- Documented the `notion_registry_multi_source` WARNING in `LOGGING_STYLE.md`. Added `notion_repair_planned` (INFO) to the Notion repair events section.
- Added a note in `OUTPUT_FORMATS.md` and `CONFIGURATION.md` that the registry database should be a standard single-data-source database; if more than one data source is found, the tool uses the first and logs a `notion_registry_multi_source` warning.

### Internals
- Deduplicated the `load_dotenv` resolver block and the test fake Notion clients.

## [1.20.0] — 2026-06-20

The Notion integration gains three new standalone modes and two lifted constraints. `--notion-prune-orphans` archives pages that were orphaned by `--notion-force-new`. `--notion-repair-database` additively fixes a registry database whose schema has drifted from the canonical layout. `--notion-company` (and `NOTION_REGISTRY_COMPANY`) adds an optional `Company` column to the registry so one database can index multiple Adobe Analytics organizations. `--watch --format notion` is now supported, publishing to Notion on the baseline cycle and on cycles where changes meet `--watch-threshold`. `--batch --format notion --workers N>1` is now supported; a process-level lock guards `.notion_pages.json` against races.

### Added
- `--notion-prune-orphans` — standalone mode; reads `.notion_pages.json` and archives (Notion trash, recoverable) every page recorded under a per-RSID `superseded` list. Preview by default; `--yes` sends the archive requests.
- `--notion-repair-database` — standalone mode; compares the live registry database schema against the canonical property list and additively creates any missing properties. Never changes existing property types; type conflicts are reported and left untouched. Preview by default; `--yes` applies. Requires a database id (`NOTION_REGISTRY_DATABASE_ID` or `--notion-registry-database`).
- `--notion-company NAME` — optional `Company` column for the registry database row; when set, the registry row key becomes `(Company, RSID)` instead of RSID alone, allowing one database to hold multiple organizations without RSID collisions. Env-var equivalent: `NOTION_REGISTRY_COMPANY`. Precedence: flag → env → Adobe global company id on the generate path; push path uses flag/env only.
- `--yes` / `-y` — confirms the two Notion destructive actions (`--notion-prune-orphans`, `--notion-repair-database`) when called without `--dry-run`.
- New debug events now emitted: `notion_registry_property_missing` (DEBUG, fired when an optional registry property is absent from the live database), `notion_registry_skipped` (DEBUG, fired when no database id resolves and the registry step is skipped).

### Changed
- `--watch --format notion` is now supported. Notion publishes on the baseline cycle and on every `change` event (cycles where `total_changes >= --watch-threshold`). Zero-change cycles and fetch-error cycles never publish.
- `--batch --format notion --workers N>1` (parallel batch with Notion output) is now supported. A process-level lock serializes writes to `.notion_pages.json` so concurrent workers do not race. Note: Notion's API rate limit is approximately 3 requests/s; the client retries HTTP 429 responses automatically.
- `.notion_pages.json` per-RSID value is now `{"current": "<page_id>", "superseded": ["<old_id>", ...]}`. The previous flat shape (`{rsid: page_id}`) still loads without migration.

### Internals
- `output/notion_registry.py`: `collect_superseded` / `drop_superseded` helpers for the `superseded` list; `_REGISTRY_LOCK` (`threading.Lock`) guards all atomic registry writes so parallel workers are safe.
- `output/notion_database.py`: `PROPERTY_SCHEMA` dict is now the single canonical source of truth for the registry database schema. `repair_database()` uses it to compute the diff. The `Company` `rich_text` property is part of the schema and is created by `--notion-repair-database --yes` when absent.
- New event: `notion_property_created` (INFO, emitted by `--notion-repair-database --yes` for each property added), `notion_repair_type_conflict` (WARNING, reported when a property's existing type differs from the canonical type), `notion_repair_complete` (INFO), `notion_prune_planned` (INFO), `notion_page_archived` (INFO), `notion_page_archive_failed` (WARNING), `notion_prune_complete` (INFO), `notion_watch_publish_failed` (WARNING, emitted when Notion publish raises during a watch cycle — the cycle continues).

## [1.19.0] — 2026-06-19

Notion gains an opt-in **SDR Registry database**: one database row per RSID, keyed by an `RSID` rich-text property, with a `url` link to the v1.18.0 detail page. The local `.notion_pages.json` registry shape is unchanged.

### Added
- `NOTION_REGISTRY_DATABASE_ID` env var — when set, `--format notion` and `--push-to-notion` runs also upsert a row into the named Notion database after writing the detail page.
- `--notion-registry-database <id>` — CLI override for the env var.
- `--no-notion-registry` — opt out of the database upsert for one run even when the env var is set.
- `--notion-print-database-schema` — fast-path command that prints the canonical property names and types so manual database setup is mechanical.

### Forward-compat
- `.notion_pages.json` shape is unchanged. v1.18.0 registries load on v1.19.0 with no migration. Database row IDs are not persisted locally; they are recovered each run via `data_sources.query` keyed by the `RSID` property.

### Constraints
- `--watch --format notion` and `--batch --format notion --workers N>1` remain rejected (v1.18.0 rationale unchanged).
- Naming `--notion-registry-database` and `--no-notion-registry` together, or naming either of them without `--format notion` / `--push-to-notion`, exits `ExitCode.USAGE`.
- AA invariants (read-only, 2.0-only) untouched — the Notion writer never imports `aanalytics2`; meta-tests under `tests/meta/` are unaffected.

### Internals
- New module `output/notion_database.py` — row property builder and upsert. `output/notion_client_guard.py` extended to resolve the optional database ID alongside the existing token + parent page ID. Per-run `database_id` / `disable_registry` set as instance attributes on the `NotionWriter` singleton in `pipeline/single.py`, same pattern v1.18.0 uses for `force_new`.

## [1.18.0] — 2026-05-14

Notion is now a first-class output destination. `--format notion` publishes the SDR directly to a Notion page; `--push-to-notion <file>` republishes an existing JSON artifact or snapshot envelope without re-calling the Adobe Analytics API. Idempotent by RSID — re-runs update the existing page in place.

### Added
- `--format notion` — publish SDR directly to a Notion page in a single command.
- `--push-to-notion <file>` — push an existing SDR JSON or snapshot envelope (`aa-sdr-snapshot/v[1-4]`) to Notion without contacting the AA API.
- `--notion-force-new` — force a brand-new Notion page even if one already exists for the RSID; the new ID replaces the old entry in `.notion_pages.json`.
- Idempotent page registry (`.notion_pages.json`) keyed by RSID — atomic JSON via `core.json_io.write_json`. Registry path: `--output-dir` if set, else input file's parent (push) or CWD (generate).
- `notion` optional extra: `uv pip install 'aa-auto-sdr[notion]'` (bundles `notion-client>=2.0.0`).

### Constraints
- `--watch --format notion` rejected by `_validate_notion_modifiers` in `cli/main.py._dispatch()` (returns `ExitCode.USAGE`) — silent loops over the same page aren't useful in v1.
- `--batch --format notion --workers N>1` rejected similarly — concurrent writes to `.notion_pages.json` would race; run batch serially.
- AA read-only and API 2.0-only invariants preserved — the Notion writer never imports `aanalytics2`; meta-tests under `tests/meta/` are untouched.

### Internals
- New writer module `output/writers/notion.py` implementing the existing `Writer` protocol; self-registers in `output.registry.bootstrap()`. Per-run `force_new` set as an instance attribute by `pipeline/single.py` (same singleton-mutation pattern `excel-template` uses for `template_path`).
- Pure block builder in `output/notion_blocks.py` — accepts an `SdrDocument` or a normalized dict so the push path can reuse it without reconstructing a document.
- `output/notion_client_guard.py` isolates the `notion-client` import behind `_require_notion_client` so tests can patch a single guard regardless of whether the extra is installed.

### Forward-compat (v1.19 preview)
- v1.19 is planned to introduce an **SDR Registry database** in Notion: one database row per report suite, with metadata as properties (last updated, component counts) and a relation to the detail page. The v1.18.0 page structure and `.notion_pages.json` registry file are forward-compatible with that design — no breaking changes to the v1.18.0 envelope.

## [1.17.0] — 2026-05-14

`--snapshot-dir` now composes with all snapshot-aware actions. Previously the flag was honored only by `--snapshot`, `--batch`, `--trending-window`, and `--watch`; four commands ignored it and resolved exclusively from `--profile`. No new flags.

### Changed
- `--list-snapshots` and `--prune-snapshots` accept `--snapshot-dir` as an
  alternative to `--profile`. Both previously required `--profile`; now either
  `--profile` or `--snapshot-dir` is sufficient. Error message updated to name
  both flags.
- `--diff` and `--compare-with-prev` use `--snapshot-dir` as the snapshot
  store when resolving `<rsid>@latest`, `<rsid>@previous`, and
  `<rsid>@<timestamp>` tokens. Filesystem paths and `git:` tokens are
  unaffected. `--snapshot-dir` takes precedence over `--profile` (consistent
  with generate/batch/watch behavior since v1.13.0).
- `--diff` and `--compare-with-prev` invoked with neither `--profile` nor
  `--snapshot-dir` now fall back to `~/.aa/orgs/default/snapshots` when
  resolving profile-form tokens, instead of erroring with
  `requires --profile`. This aligns the no-flags behavior with
  generate/batch/watch/trending (which have used the same default-profile
  fallback since v1.13.0). Filesystem paths and `git:` tokens are still
  resolved without touching the snapshot store.
- `--snapshot-dir` help text updated to reflect full command coverage. The
  `--list-snapshots` and `--prune-snapshots` action help strings now name
  both `--profile` and `--snapshot-dir` as acceptable scopes.

## [1.16.1] — 2026-05-12

Fast-fail VRS fetch on the empty-tenant / permanent-shape error mode that
previously burned ~90 s of pointless retries before degrading. The exhaust
path now collapses to ≤ 3 s, and a new additive `vrs_unavailable` WARNING
points operators at the real cause instead of leaving them to interpret a
generic `TransientApiError`.

### Fixed
- `KeyError('content')` raised by `aanalytics2` 0.5.1 on a VRS-list response
  that lacks the `content` key (common on tenants with zero VRS or during
  Adobe-side 5xx) is now classified as permanent on the VRS path only via a
  new `VrsEndpointShapeError(ApiError)`. The resilience layer's retry policy
  skips it; all three VRS rungs in `fetch_virtual_report_suites` (count-only
  fast path, full rung, minimal rung) fail-fast and graceful-degrade. No
  behavior change for any other fetcher.

### Added
- `core.exceptions.VrsEndpointShapeError(ApiError)` — typed signal for the
  permanent VRS-endpoint shape failure.
- `api.resilience.classify_permanent_vrs_shape_error(fn)` — innermost guard
  used by the three VRS SDK call sites.
- `vrs_unavailable rsid=… likely_cause=empty_tenant_or_permanent_endpoint_shape_error`
  WARNING emitted additively alongside the existing exhausted/count-only WARNING
  when the cause of exhaust is the permanent shape error. The existing
  warning's `error_class=` field now reads `VrsEndpointShapeError` rather
  than `TransientApiError`, which is itself a useful operator signal.

## [1.16.0] — 2026-05-12

Template-fill Excel writer. Pointing `--template /path/to/aa_en_BRD_SDR_template.xlsx` at an existing Adobe BRD/SDR `.xlsx` switches the Excel writer to fill mode: each data sheet is located by name + section anchor, the header row is detected by content, and API-derived component data is filled into the rows below — preserving styles, cross-sheet formulas, defined names, column widths, page setup, and every cell the writer doesn't explicitly touch.

### Added
- `--template PATH` modifier flag. Required readable `.xlsx`. When set, every
  resolved `excel` format slot is swapped to `excel-template` (the new format
  key). Aliases (`all` / `reports`) keep producing `excel`; the swap happens
  after alias resolution.
- `--template-organization NAME` modifier flag. String written to
  `Glossary!C2` (the cell every other sheet's `C2` formula references for the
  brand banner). Defaults to the report suite name. Requires `--template`.
- New writer module `output/writers/excel_template.py` (`ExcelTemplateWriter`)
  self-registers under the `excel-template` format key.
- New pure helper module `output/_template_anchors.py` for header detection.
- 5 new logging events: `template_load`, `template_sheet_filled`,
  `template_sheet_skipped`, `template_overflow`, `template_sheet_clipped`.
  The clip event fires when more API components remain than the soft cap
  (max_row + 50) can hold; drops are logged with the count, never silent.

### Dropped (from the v1.16.0 roadmap)
- `--template-overwrite-reserved` — argparse-rejected. The spike listed this
  as a hedge for customer-edited reserved-component rows (`pageName`,
  `linkName`, `campaign`). The cleaner uniform rule is match-by-id, always
  overwrite when the API has data for that id. Customers who hand-edit
  descriptions should edit after generation; the API is the source of truth
  for this writer. Compression posture: 2/3.

### Behavior
- Default behavior unchanged: `--format excel` without `--template` produces
  output byte-equivalent to v1.15.1 (writer-from-scratch path).
- Read-only AA 2.0 invariant preserved: `openpyxl` writes target local
  `.xlsx` files only, never the Adobe Analytics API.
- No new exit codes. Template-validation failures use USAGE (2). openpyxl
  runtime errors bubble as GENERIC (1).
- No snapshot envelope schema bump (still `aa-sdr-snapshot/v4`).
- Watch mode rejects `--template` (NDJSON change-stream posture, not
  file-output workflow). Agent mode naturally rejects via its forced
  `--format json --output -` preset.

### Dependencies
- `openpyxl >= 3.1.0` promoted from dev-deps to runtime deps.

## [1.15.1] — 2026-05-12

Patch release closing three deliberately-deferred items from v1.15.0.

### Added
- `--snapshot-dir <path>` now works for single + batch dispatch
  (was silently ignored — only watch + trending consumed it
  previously). The snapshot directory (and therefore the git repo
  `--git-commit` operates on) can now live anywhere, independent
  of profile resolution.
- Auto-generated watch commit messages now include a
  `(watch cycle <n>)` footer. User-supplied `--git-message <text>`
  remains verbatim — no footer appended.

### Documentation
- Documented the v1.15.0 batch git exit-code escalation behavior
  in the v1.15.0 entry and in AGENTS.md.

### Internal
- Extracted `resolve_snapshot_dir(ns)` from `cli/commands/watch.py` to
  `cli/commands/_shared.py` so generate / batch / watch share one
  precedence chain (`--snapshot-dir > --profile > "default"`). No
  behavioral change for watch mode.

### Behavior
- Default behavior unchanged. No new CLI flags, no new exit codes, no
  envelope schema bump, no new runtime dependencies.
- Read-only AA 2.0 invariant preserved.

## [1.15.0] — 2026-05-11

Git integration. After saving a snapshot (one-shot, batch, or watch cycle),
`--git-commit` stages and commits the per-RSID pathspec to the snapshot
directory's git repo, auto-initializing the directory as a repo on first
use. `--git-push` pushes after each commit. `--git-message` overrides
the auto-generated commit message. Composes naturally with watch mode:
every baseline/change cycle commits, closing the agent-native loop.

### Added
- `--git-commit` modifier flag. After saving a snapshot, stage
  `<snapshot_dir>/<rsid>/*` and commit. Auto-inits the snapshot dir as a
  git repo on first invocation (`.git/`, `README.md`, `commit.gpgsign=false`
  set locally to avoid unattended GPG prompts). Skips commit when there
  is no staged diff (`git diff --cached --quiet`).
- `--git-push` modifier flag. Pushes after a successful commit. Requires
  `--git-commit`. Reads the user's existing `git config` for remote /
  branch / auth — we don't manage credentials.
- `--git-message <text>` modifier flag. Overrides the auto-generated
  commit message verbatim (no template interpolation). Requires
  `--git-commit`.
- `snapshot/git.py` extensions (~150 LOC): `GitOpResult` dataclass,
  `is_git_repository`, `git_init_snapshot_repo`, `git_commit_snapshot`,
  `generate_commit_message`. Reuses the existing `subprocess`-based
  pattern from `git_show` (read path) — no new dependencies.
- `pipeline/single.py`, `pipeline/batch.py`, `pipeline/watch.py` compose
  `git_commit_snapshot` on top of `save_snapshot` without duplicating
  logic. `RunResult.git_op` and `CycleResult.git_op` are new optional
  fields carrying the `GitOpResult` outcome.
- Watch event payload gains an optional `git` block on baseline/change
  events when `--git-commit` is set: `{"committed": bool, "commit_sha":
  str, "pushed": bool}`. On git failure, the original baseline/change
  event still emits, followed by a separate `error` event with
  `error_type="GitCommitError"` or `"GitPushError"`. Schema version
  unchanged (`aa-watch-event/v1` — the additions are additive).
- Three canonical log events: `git_init_repo` (path, initial_commit),
  `git_commit_complete` (rsid, commit_sha, pushed, duration_ms),
  `git_op_failed` (rsid, op, error_class, duration_ms).
- Pre-dispatch validator (`_validate_git_modifiers`) rejects `--git-push`
  and `--git-message` without `--git-commit`, and rejects `--git-commit`
  with non-generating actions (`--diff`, `--stats`, `--list-X`,
  `--trending-window`, `--compare-with-prev`, `--inventory-summary`).

### Roadmap deviations (dropped)
The v1.15.0 row listed "`--git-commit`, `--git-push-on-change`, etc." —
two flags drop from this release.

- **Dropped `--git-init`** — argparse-rejected. cja's `--git-init` is a
  standalone action that initializes a snapshot directory as a git repo.
  aa replaces it with **lazy auto-init**: the first invocation of
  `--git-commit` on a non-repo directory automatically runs the same
  initialization sequence. Detecting `is_git_repository(snapshot_dir)`
  and `git init`-ing if absent costs nothing and matches the agent-mode
  posture of "configure once, run many."
- **Dropped `--git-push-on-change`** — argparse-rejected. The roadmap
  suffix was redundant. `--git-commit` already short-circuits on no-diff
  (`git diff --cached --quiet` skips no-op commits), so "push only on
  change" is the natural behavior of `--git-push` after `--git-commit`.
  The shorter name is cja's; we adopt it for cross-tool UX parity.

Both dropped flags are allowlisted in
`tests/docs/test_agents_md_canonical_sections.py` (v1.10–v1.14 pattern).

### Behavior
- Default behavior unchanged (no `--git-commit` flag → byte-equivalent
  output to v1.14.0).
- Read-only AA 2.0 invariant preserved: git writes are local-filesystem,
  not AA-side.
- Exit codes unchanged. Reuses `ExitCode.SNAPSHOT` (16) on one-shot git
  failure. **Diverges from cja** (which warns and exits 0) for the
  agent-mode deterministic-exit contract.
- Batch git failures escalate to `PARTIAL_SUCCESS` (14) when every SDR
  generated successfully but one or more per-RSID git operations failed.
  Each failed RSID's `error_kind` and `error_message` are surfaced on
  stderr. Matches the single-mode `SNAPSHOT` (16) divergence from cja
  for the agent-mode deterministic-exit contract. If every SDR also
  failed, the existing batch-all-failed precedence still applies.
- Snapshot envelope schema unchanged (v4 from v1.12.0 carries forward).
- No new env vars, no new runtime dependencies (stdlib `subprocess` only).
- Auto-init is idempotent on existing repos.
- `commit.gpgsign=false` is set per-repo via `git config --local`; users
  who want GPG-signed snapshot commits can `git config --unset` inside
  the snapshot dir.

### Internal
- `snapshot/git.py` was previously 44 LOC of read-only `git_show`. v1.15.0
  extends it to ~200 LOC. The boundary holds: every git operation is a
  thin subprocess wrapper. Business logic lives in the pipeline
  orchestrators.
- `RunResult.git_op: GitOpResult | None` and `CycleResult.git_op:
  GitOpResult | None` are additive. Existing consumers ignore the new
  field unchanged.

## [1.14.0] — 2026-05-10

Watch mode. Enters a foreground monitoring loop that fetches, snapshots, and diffs a set of report suites on a repeating interval — emitting structured NDJSON events on stdout so agents and CI pipelines can react to changes without polling the tool themselves.

### Added
- `--watch <RSID>...` — enter the monitoring loop for one or more report suites.
- `--interval Nh|Nd|Nw` — cycle interval, required with `--watch`. Same duration grammar as `--trending-window` and `--keep-since` (e.g. `1h`, `6h`, `1d`).
- `--watch-threshold N` (default `1`) — minimum total change count to emit a `change` event. Pass `0` to emit every cycle including zero-change cycles (heartbeat mode).
- Three canonical log events: `watch_loop_start` (INFO, fires once at dispatch entry, carries `rsids` count, `interval`, `watch_threshold`); `watch_cycle_complete` (INFO, fires once per emitted NDJSON event, carries `cycle`, `rsid`, `change_count`, `emitted`); `watch_loop_stop` (INFO, fires at loop termination, carries `reason` and `cycles_completed`).
- `aa-watch-event/v1` NDJSON schema. Three event types emitted on stdout:
  - `baseline` — first cycle for an RSID, always emitted (no previous snapshot to diff against).
  - `change` — subsequent cycle where `total_changes >= watch_threshold`.
  - `error` — per-RSID fetch failure within a cycle; loop continues.
- `cli/commands/watch.py` (NEW) — watch command entry point and `_LoggingEmitter`.
- `pipeline/watch.py` (NEW) — cycle orchestrator; calls the existing single-RSID fetcher, snapshot store, and comparator.
- `output/watch_event.py` (NEW) — NDJSON event serializer; timestamps are Z-suffixed ISO-8601.
- `redact_text` public alias in `core/logging.py` — scrubs Bearer tokens and secrets from error message strings before they are included in `error` events.

### Roadmap deviations (dropped)
- **`--on-change` is not shipped.** The original roadmap item envisioned a subprocess hook. In practice, `--watch-threshold` controls emission precisely and stdout NDJSON already gives downstream consumers a clean event stream to react to. The v1.10–v1.13 pattern of compressing roadmap complexity into the fewest orthogonal flags applies here: `--watch | jq -c . | xargs ...` is the composable form, not a built-in subprocess spawner. Argparse rejects `--on-change` with the standard unrecognized-argument error.

### Rejected with `--watch`
- `--format` — watch emits NDJSON directly on stdout; per-run output formats do not apply. Rejected with `USAGE` (2).
- `--quality-policy` — the quality engine runs on a completed SDR document; the watch loop does not assemble one. Rejected with `USAGE` (2).
- `--fail-on-quality` — same rationale as `--quality-policy`. Rejected with `USAGE` (2).
- `--interval` or non-default `--watch-threshold` without `--watch` — rejected by the pre-dispatch validator with `USAGE` (2).

### Unchanged
- Default behavior (single SDR / batch / diff / inspect / discovery) — byte-equivalent to v1.13.0.
- Snapshot envelope schema — still `aa-sdr-snapshot/v4` from v1.12.0.
- Exit codes — SIGINT / SIGTERM exit `0`; no new codes added.
- SDK surface — no new `aanalytics2` methods called beyond the existing read surface.
- Environment variables and runtime dependencies — no additions.

## [1.13.0] — 2026-05-10

Drift / trending windows. Applies the snapshot comparator across a
window of snapshots for a single RSID, producing a per-RSID
time-series of component lifecycle counts plus a derived drift
summary. Two new actions ship; one roadmapped flag dropped.

### Added
- `--trending-window <duration> <RSID>...` action — emits a per-RSID
  time-series report from existing snapshot files. Duration grammar
  is `Nh|Nd|Nw` (reuses the retention parser). Default no default —
  duration is required. Three output formats: `console` (default),
  `json` (schema `aa-trending/v1`), `markdown`. Multi-RSID renders
  per-RSID blocks (console / markdown) or wraps in
  `{"reports": [...]}` (json).
- `--compare-with-prev <RSID>...` action — sugar for
  `--diff <RSID>@previous <RSID>@latest`. Uses the existing diff
  resolver, output formats, and flag set. Multi-RSID loops; worst
  exit code wins.
- `snapshot/trending.py` (NEW) — `compute_trending()` orchestrator
  + 6 frozen dataclasses (`WindowSpec`, `ComponentCounts`,
  `LifecycleDelta`, `SnapshotPoint`, `DriftSummary`,
  `TrendingReport`).
- `--snapshot-dir <path>` non-mutex flag — overrides the active
  profile's snapshot directory. Composes with `--trending-window`
  in v1.13.0; other snapshot-aware actions (`--diff`,
  `--list-snapshots`, `--prune-snapshots`) still resolve from
  `--profile` only — opt-in retrofit possible later. Default
  `None` (no behavior change for existing flows).
- `snapshot/_duration.py` (NEW) — `parse_duration()` shared by
  retention (`--keep-since`) and trending (`--trending-window`).
  Pure refactor; existing retention behavior unchanged.
- `output/trending_renderers/` (NEW) — three renderer modules.
- Two INFO log events: `trending_window_resolved` (carries
  `duration`, `start_at`, `end_at`); `trending_compute_complete`
  (carries `rsid`, `snapshot_count`, `total_changes`,
  `volatility_score`).

### Roadmap deviations (dropped)
The v1.13.0 row listed three flags; this release ships two.
- **Removed `--include-drift`** — argparse-rejected. cja's
  `--include-drift` triggers a cross-data-view drift score in its
  org-report flow. aa has no org-report; drift in aa is per-RSID
  lifecycle churn, which is the natural output of `compare()`. A
  separate flag would either duplicate `--trending-window` output
  or invent an aa-specific score and gate it behind redundant
  opt-in. Drift summary is **always included** in
  `--trending-window` output; the cost is a single dict
  comprehension over already-computed `ComponentDiff` records.

Test rejection in `tests/cli/test_v1_13_flags.py` ensures the
removed flag receives a clear argparse error.

### Behavior
- Default behavior unchanged. Both new actions are opt-in.
- `--trending-window` reads existing snapshot files only — no AA
  API calls, no SDR rebuild, no auth required.
- `--trending-window` requires positional RSIDs (no auto-discover);
  no positional → `ExitCode.USAGE` (2).
- Empty window for one RSID → warning + `PARTIAL_SUCCESS` (14);
  empty for all RSIDs → `NOT_FOUND` (13).
- Window upper bound is "now at compute time," not "the most recent
  snapshot's timestamp" — a snapshot taken just outside the window
  is excluded even if it's the most recent on disk.
- `--include-drift` is argparse-rejected; CHANGELOG explains.
- No new exit codes. No new exception classes. No new env vars. No
  new runtime dependencies. No SDK surface change.
- Snapshot envelope schema unchanged (v4 from v1.12.0 carries
  forward).

### Internal
- `snapshot/retention.py::_DURATION_RE` and `_UNIT_TO_HOURS`
  removed; replaced with `from aa_auto_sdr.snapshot._duration
  import parse_duration`. Existing retention tests stay green.
- `snapshot/retention.py::_restore_iso` renamed to
  `restore_iso` (dropped leading underscore — promoted to public
  cross-module API). `snapshot/trending.py::_path_in_window`
  uses it to filter snapshot files into the trending window
  without parsing JSON. No external callers existed before
  v1.13.0 — verified by `grep -rn "_restore_iso"` returning
  zero matches outside `retention.py` itself.

## [1.12.1] — 2026-05-10

Patch release. Polish on top of v1.12.0's quality-engine surface — log
correlation in batch runs, a tighter logging-vocabulary validator, and a
documentation note on a small JSON-output shape change. No new flags, no
new exit codes, no behavior changes for existing flows.

### Changed
- `quality_audit_complete` and `quality_gate_evaluated` log events
  now include the `rsid` extras key. Multi-RSID `--batch` runs can
  correlate every audit / gate decision back to a specific RSID
  without parsing log message bodies. Empty string when the caller
  doesn't supply one (direct `run_audits()` use in tests).
- The two events' message format strings now use keys that match
  their `extra` dict keys exactly (`quality_total=`,
  `quality_by_severity=`) — pre-v1.12.1 the message used `total=` and
  `by_severity=`, which the canonical-event vocabulary validator
  could not unambiguously match against extras keys.

### Fixed
- `tests/core/test_logging_vocabulary.py` validator now uses
  word-boundary matching when inspecting log-message format strings,
  so substring collisions like `severity=` inside `quality_by_severity=`
  no longer false-positive. `src/aa_auto_sdr/sdr/quality.py` is now
  in the instrumented-modules set, so the quality engine's emissions
  are validated alongside other instrumented surfaces.

### Documented
- `PerRsidResult` (the per-RSID record in `--run-summary-json` output)
  carries a new `quality_verdict: str` field as of v1.12.0. The field
  is empty (`""`) when no audits ran; `"pass"` / `"fail"` / `"n/a"`
  when audits + `--fail-on-quality` were active. JSON consumers that
  ignore unknown keys are unaffected; consumers with strict-key
  schemas should add the field to their allowlist. (This shape
  change shipped in v1.12.0; the CHANGELOG note was missed there.)

### Internal
- `tests/cli/test_v1_12_flags.py`: hoisted `argparse` / `logging`
  imports to module top; replaced `cli_main.logger.name` attribute
  reads with the literal `"aa_auto_sdr.cli.main"` so a future logger
  rename surfaces as a clear test failure rather than a silent
  miss-match.
## [1.12.0] — 2026-05-10

Quality severity engine. Promotes v1.9.0 naming-audit findings to a
five-level severity ladder (CRITICAL > HIGH > MEDIUM > LOW > INFO),
adds machine-readable quality reports, and gates CI on quality
breaches via `--fail-on-quality`. Activates the v1.8.0 ValidationCache
scaffold as its first production caller.

### Added
- `--quality-report {json,csv}` — emit a standalone machine-readable
  quality report alongside SDR output. Default filename
  `quality_report_<RSID>_<timestamp>.{json,csv}`.
- `--quality-policy <path>` — JSON policy file. Top-level keys
  `fail_on_quality` and `quality_report`. CLI flags always win over
  policy values. Hyphen / underscore canonicalization; optional
  `quality_policy` / `quality` envelope nesting.
- `--fail-on-quality {CRITICAL,HIGH,MEDIUM,LOW,INFO}` — exit
  `ExitCode.QUALITY` (17) if any issue at or above the threshold
  exists. SDR output and snapshot still emit normally.
- `ExitCode.QUALITY = 17` — new soft-signal exit code (parallel to
  `WARN = 3`); CI-actionable.
- `sdr/quality.py`: `SeverityLevel` (StrEnum), `Issue` (frozen
  dataclass), `run_audits` orchestrator that severity-promotes
  v1.9.0 findings.
- `sdr/quality_policy.py` (NEW) — policy loader, defaults applier,
  report writer.
- ValidationCache integration: `quality.run_audits` is the first
  production caller of the v1.8.0 LRU+TTL cache. Cache key includes
  the severity-table version so v1.12.x mapping changes invalidate.
- Snapshot envelope schema bumps v3 -> v4. Two additive keys inside
  the `quality` block: `issues` and `summary`. v3 envelopes still
  load on v1.12.0.

### Fixed
- `SdrDocument.to_dict()` previously dropped `quality` and
  `fetch_status`. Long-standing gap surfaced by the v1.12.0 work and
  fixed in this release. JSON output for v1.9.0-v1.11.0 users now
  carries the quality block; downstream consumers that ignore
  unknown keys are unaffected.

### Roadmap deviations (dropped)
The v1.12.0 row listed three flags; this release ships all three.
Compression happens at the **policy-schema** and **architecture**
levels:
- **Removed `max_issues` policy key.** cja's policy schema caps issue
  output at N. aa's quality block is compact (severity-promoted v1.9.0
  findings only; no risk of multi-thousand-issue payloads).
- **Removed `allow_partial` policy key.** cja uses this with
  `--fail-on-quality`. aa already has `PARTIAL_SUCCESS` (14) and
  `QUALITY` (17) as orthogonal exit codes.
- **No pandas dependency.** aa's checks operate on normalized
  dataclasses, not dataframes.
- **No per-RSID parallel checks.** aa parallelizes at the batch level
  (v1.8.0); per-RSID checks are O(hundreds), sub-50ms uncached.

Test rejections in `tests/sdr/test_quality_policy.py` ensure the
removed policy keys raise `ConfigError`.

### Behavior
- Default behavior unchanged. None of the three new flags are on by
  default. Existing v1.9.0 audits run with the same outputs plus two
  new keys (`issues`, `summary`) inside the quality block.
- `--quality-report` or `--fail-on-quality` without `--audit-naming` /
  `--flag-stale` auto-enables both audits (logged as
  `quality_auto_enabled`).
- Quality flags outside SDR generation (`--stats`, `--list-X`,
  `--inventory-summary`, `--diff`) exit `USAGE` (2).
- Batch precedence: `PARTIAL_SUCCESS` (14) outranks `QUALITY` (17).
  Build failures are more actionable than quality verdicts; users
  fixing partial failures re-run and then see the gate.
- `BatchResult` gains `quality_verdicts: dict[str, str]` (default
  empty).
- No new exception classes (reuse `ConfigError`). No new env vars.
  No new runtime dependencies.

## [1.11.0] — 2026-05-10

First post-Tier 2 release. `--inventory-summary` cross-RSID aggregate
rollup. One flag adapted from cja's inventory family; one dropped
because the cja semantic doesn't translate to AA's data model.

### Added
- `--inventory-summary [RSID...]` action — emits a cross-RSID
  aggregate rollup of component counts (totals, min, max, avg per
  component type) plus a per-RSID detail block. With no positional
  RSIDs, summarizes every visible report suite (mirrors `--stats`
  precedent). Three output formats: `table` (default), `json`, `csv`.
  Reuses the v1.7.2 `count_only` fetcher path — no new SDK surface.
  Lives in the existing `actions` mutex argparse group, so combining
  it with `--stats` / `--describe-reportsuite` / `--list-X` yields a
  clean argparse error.
- `cli/commands/inventory.py` (NEW) — `run()` handler + `_aggregate()`
  pure helper.

### Roadmap deviations (dropped)
The v1.11.0 row in the roadmap listed two flags; this release ships
one. One flag deliberately removed during spec design:
- **Removed `--inventory-only`** — argparse-rejected. cja uses this
  flag to drop "standard SDR sections" and emit only the inventory
  sheets (`output/inventory/`). aa's SDR document treats calculated
  metrics + segments as first-class sections; aa already has
  `--metrics-only` / `--dimensions-only` (v1.2.0) for component-type
  filtering and `--list-calculated-metrics` / `--list-segments` for
  detail. A separate `--inventory-only` would either duplicate those
  or invent a redundant filter mode.

Test rejection in `tests/cli/test_v1_11_flags.py` ensures the removed
flag receives a clear argparse error.

### Behavior
- Default behavior unchanged. `--inventory-summary` is opt-in.
- `--inventory-summary --format excel` errors with `ExitCode.OUTPUT`
  (15). Allowlist is `{table, json, csv}`.
- Per-RSID fetch failures mark the per-RSID row's components with
  `*` in table output and add a footer disclaimer; `fetch_status`
  appears on the per-RSID JSON row when at least one component is
  non-healthy. Mirrors `--stats` exactly.
- No new exit codes. No new exception classes. No new env vars. No
  new runtime dependencies (stdlib `csv`, `json`).
- No SDK surface change. Snapshot envelope schema unchanged (v3
  carries forward).

## [1.10.0] — 2026-05-09

Tier 2 milestone closes: `--batch` sampling. Three flags adapted from
the CJA `--sample` family; two roadmap-listed flags deliberately
dropped because they target a CJA-only data structure that aa
doesn't build. Mirrors the v1.8.0 (dropped 2/8) and v1.9.0 (dropped
4/8) compression pattern.

### Added
- `--sample N` flag (`--batch`-only): subset N RSIDs from the batch
  list before dispatch. `N >= 1`. When `N >= len(batch)`, the full
  list runs and `BatchResult.sampled = False` (no-op).
- `--sample-seed N` flag: integer RNG seed for reproducible sampling.
  Default: non-deterministic (Python's `random` default).
- `--sample-stratified` flag: group RSIDs by code prefix (split on
  first `.` / `_` / `-`); sample proportionally per group. Without
  this flag, sampling is uniform random.
- Four sampling fields on `BatchResult`: `sampled` (bool),
  `sample_size` (int | None), `sample_seed` (int | None),
  `total_available` (int). All default-valued so existing callers
  continue to construct `BatchResult` unchanged.
- Logging vocabulary gains three keys — `sample_size` (int),
  `sample_seed` (int | None), `sample_strategy` (str: `random` or
  `stratified`) — plus `count_total` (int) for the canonical
  pre-sample population size. All four allowlisted in
  `tests/core/test_logging_vocabulary.py`.
- New canonical INFO event `batch_sampled` (single record per
  sampled batch). Carries `count`, `count_total`, `sample_size`,
  `sample_seed`, `sample_strategy`. Fires only when sampling
  actually applied (`sample_size < len(batch)`).
- `pipeline/sampling.py` (NEW) — pure RNG-driven sampler with
  random and stratified strategies.

### Changed
- `pipeline/batch.py::run_batch` gains three keyword-only sampling
  parameters (`sample_size`, `sample_seed`, `sample_stratified`).
  Existing callers that don't pass them get the v1.9.0 sequential
  / parallel paths unchanged.
- Batch summary banner prints
  `Sampled X of Y RSIDs (strategy=random[, seed=N])` when sampling
  was applied; otherwise the v1.9.0 banner is byte-equivalent.

### Roadmap deviations (dropped)
The v1.10.0 row in the roadmap listed five flags; this release
ships three. Two flags were deliberately removed during spec design:
- **Removed `--memory-limit`** — argparse-rejected. CJA uses this
  flag to guard a cross-DataView component-index dict that aa does
  not build (batch streams to disk; `ValidationCache` is bounded).
  No surface to guard.
- **Removed `--memory-warning`** — argparse-rejected. Same rationale.

Test rejections in `tests/cli/test_v1_10_flags.py` ensure the two
removed flags receive a clear argparse error.

### Behavior
- Default batch invocations (no `--sample`) are byte-equivalent to
  v1.9.0, modulo four extra default-valued fields on `BatchResult`
  (`sampled=False`, `sample_size=None`, `sample_seed=None`,
  `total_available=len(batch)`).
- Per-RSID SDR documents and snapshot files are byte-identical to
  v1.9.0.
- Mode-scoping: `--sample`, `--sample-seed`, `--sample-stratified`
  outside `--batch` exit with `ExitCode.USAGE` (2) and a clear
  error message.
- `--sample N` where `N >= len(batch)` is a no-op: full list runs,
  `BatchResult.sampled = False`.
- No new exit codes. No new exception classes. Snapshot envelope
  schema unchanged (v3 carries forward).

### Other
- Coverage gate ≥90% preserved.
- Vocabulary meta-test extended to recognize the new logging keys.

## [1.9.0] — 2026-05-09

Tier 2 milestone: field-level shaping + naming audits. Four CJA-port
flags adapted to aa_auto_sdr's surface; four roadmap-listed flags
deliberately dropped because they target CJA-only data-model concepts
or are redundant in AA's per-RSID SDR generation (which already
includes names + metadata by default).

### Added
- `--audit-naming` flag: adds a `quality.naming_audit` block to the SDR
  document with case-style counts, prefix groupings, and recommendations
  for mixed-style component sets. Pure post-build pass; no extra API
  calls.
- `--flag-stale` flag: adds a `quality.stale_components` block to the
  SDR document listing components matching stale-keyword regex
  (test/old/temp/deprecated/etc.), version-suffix regex (`_vN`), or
  date-pattern regex (`YYYYMMDD` or `YYYY-MM-DD`). Reasons recorded
  per component.
- `--name-match {exact,insensitive,fuzzy}` flag (default: `insensitive`):
  resolution strategy for `<RSID_OR_NAME>` lookups across all commands.
  `fuzzy` uses `difflib.SequenceMatcher` at threshold 0.85.
- `--extended-fields` flag (in `--diff` mode): includes noisy fields
  (description, tags, category, data_group, extra, compatibility,
  categories, owner_id, created, modified) in diff output. Off by
  default — these fields are now suppressed in default diff output.
- `quality` field on `SdrDocument` (default `None`); top-level `quality`
  key on snapshot envelopes (schema bumped v2 → v3, additive +
  backward-compat).
- New `core/exceptions.py::AmbiguousMatchError` (extends `AaAutoSdrError`,
  maps to existing `ExitCode.NOT_FOUND`).
- `name_match_strategy` log field activated.
- `sdr/quality.py` (NEW) — pure naming-audit + stale-detection module.

### Changed
- `snapshot/comparator.py::compare`: noisy fields (description, tags,
  category, etc.) are now suppressed from diff output by default.
  Pre-v1.9.0 behavior is restored by passing `--extended-fields`. Diff
  output for non-noisy field changes (id, name, type, definition) is
  byte-equivalent to v1.8.0. Note: the `extended_fields` toggle affects
  component fields only; the top-level `quality` block is not diffed
  (see Roadmap deviations — quality-block diffing is deferred).
- `api/fetch.py::resolve_rsid`: gains a keyword-only `name_match`
  parameter (default `"insensitive"`, which preserves pre-v1.9.0
  semantics). New strategies: `exact` (case-sensitive name match)
  and `fuzzy` (SequenceMatcher fallback).
- Snapshot envelope schema: `aa-sdr-snapshot/v2` → `aa-sdr-snapshot/v3`.
  v1 and v2 envelopes remain readable; v3 envelopes are not readable
  by v1.8.0 clients (existing schema-version error fires).

### Roadmap deviations (documented)
The v1.9.0 row in the roadmap listed eight flags; this release ships
four. Four flags were deliberately removed during spec design:
- **Removed `--no-component-types`** — splits "standard vs derived"
  component types, a CJA-only concept (AA has no derived fields).
- **Removed `--lock-stale-threshold`** — belongs to CJA's
  `--org-report` lock subsystem; aa_auto_sdr deliberately has no
  `--org-report` (out of scope per `CLAUDE.md`).
- **Removed `--include-names`** — aa's per-RSID SDR generation
  already includes component names by default. The cja flag exists
  because cja's `--org-report` renders a TABLE where columns are
  opt-in; AA has no equivalent table mode.
- **Removed `--include-metadata`** — aa's SDR document already
  includes report-suite metadata (timezone, segments list, etc.) by
  default.

- **Deferred — quality-block diffing.** Spec §3.6 anticipated that
  `--diff --extended-fields` would also compare `quality.naming_audit`
  and `quality.stale_components` blocks across snapshots. v1.9.0 ships
  the `quality` field on snapshots but `compare()` does not diff it.
  Quality-block diffing is deferred to a future release (likely v1.12.0
  alongside the quality severity engine), where comparison semantics for
  audit results will be designed alongside the severity model.

Test rejections in `tests/cli/test_v1_9_flags.py` ensure the four
removed flags receive a clear argparse error.

### Other
- Coverage gate ≥90% preserved.
- `quality` field is optional (None when neither audit/stale flag
  set); v1.8.0 byte-equivalence preserved for default-flag runs.
- Existing default-flag invocations produce SDR documents and
  snapshots whose deserialized component fields are byte-equivalent
  to v1.8.0 (envelope `schema` field bumps to v3 — version-string
  difference only, not a content change).

## [1.8.0] — 2026-05-09

Tier 2 milestone: parallel batch workers + validation-cache scaffolding.
Workers ship as the headline feature; the cache class lands as
infrastructure for v1.12.0's quality engine. Six v1.7.x cleanup items
deferred during v1.7.2 review also land here.

### Added
- `--workers N` flag on `--batch` runs. Default 1 (sequential, byte-equivalent to v1.7.2). Range 1..16. Uses a `ThreadPoolExecutor` with a single shared `AaClient` across worker threads. Per-RSID log records carry `worker_id` (submission index, 0..N-1).
- `--fail-fast` flag — opt-out of continue-on-error in parallel mode. First worker exception cancels pending futures. Sequential mode (`--workers 1`) ignores the flag.
- `ValidationCache` class in `src/aa_auto_sdr/api/cache.py`. Thread-safe LRU with TTL eviction; `OrderedDict` + `threading.Lock`. Mirrors cja_auto_sdr's `ValidationCache` API. **Cache target deliberately empty in v1.8.0** — no production call sites; v1.12.0's quality engine will be the first caller.
- `--enable-cache`, `--clear-cache`, `--cache-ttl SECONDS` (default 3600), `--cache-size ENTRIES` (default 1000) flags. With `--enable-cache`, a `ValidationCache` instance is constructed and passed through to the worker pool; without it, no cache exists.
- `cache_event` log field — DEBUG-level, values `hit` / `miss` / `evict` / `expire`. Emitted by `ValidationCache` operations.
- `worker_id` log field — INT, emitted on per-RSID records when running parallel. Sequential mode omits the field (preserves v1.7.2 log byte-equivalence).
- `benchmarks/` directory with `v1.7.2_count_only.py` measuring the count_only-vs-full SDK-call-shape speedup. Initial v1.8.0 numbers in `benchmarks/results.md`.

### Changed
- `pipeline/batch.py::run_batch` now dispatches sequential vs parallel based on the new `workers` keyword argument. The existing sequential implementation moves to `_run_sequential` (no behavior change). Callers without the new arg get sequential behavior unchanged.
- `cli/commands/inspect.py::run_list_classification_datasets`: `captured_status` typing tightened from `dict[str, tuple[str, str | None]]` to `dict[str, tuple[FetchStatus, str | None]]` (cleanup item C2).
- `api/fetch.py::fetch_classification_datasets`: bare `_ = count_only` no-op marker replaced with a richer comment pointing at the SDK constraint and the spec's classifications-parity section (cleanup item C6).
- `tests/core/test_logging_vocabulary.py`: `expansion_level` allowed-values extended to include `count_only` (the value already fired from v1.7.2 but wasn't in the allowlist meta-test) (cleanup item C3).

### Roadmap deviations (documented)
The v1.8.0 row in the roadmap listed eight flags; this release ships six. Three flags were deliberately removed during spec design and one new flag added:
- **Removed `--continue-on-error`** — the existing sequential default already continues on error; flag would be redundant.
- **Removed `--shared-cache`** — no implementation under threads (which natively share memory); reserved if a future release adopts a process-based worker model.
- **Removed `--use-cache`** — redundant with `--enable-cache` under our per-run cache design (cross-invocation persistence is out of scope).
- **Added `--fail-fast`** — real behavior change; opts out of the continue-on-error default in parallel mode.

Test rejections in `tests/cli/test_batch_workers_flags.py` ensure attempts to pass the removed flags receive a clear argparse error.

### Fixed
- v1.7.2 cleanup items C1–C6 (test/doc parity, type tightening, benchmark verification). See spec §2.3 for the full list and PR commit log.

### Other
- Coverage gate ≥90% preserved (target: ~92–94% post-release; baseline 93.62% post-v1.7.2).
- Sequential `aa_auto_sdr --batch` runs (without `--workers`) emit log records and snapshot envelopes byte-equivalent to v1.7.2.
- Single shared `AaClient` across worker threads — `aanalytics2` is thread-safe for the read methods this tool uses.

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
- Helpers in `cli/list_output.py`: `build_footer(records)` and `annotate_cells(records)` shared between describe + stats.

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
