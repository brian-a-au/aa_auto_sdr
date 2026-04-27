# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
- `--include-segments` / `--include-calculated` — explicit no-ops for CJA parity (segments/calc are already default in AA).

### Config introspection

- `--config-status` prints the full credential resolution chain (more verbose than `--show-config`).
- `--validate-config` validates credential shape without calling Adobe (`org_id` must end `@AdobeOrg`, all required fields present).
- `--sample-config` emits a `config.json` template to stdout.

### Breaking changes

- **`--profile-import` no longer silently overwrites an existing profile.** It now exits 10 with a remediation message; pass `--profile-overwrite` to allow replacement. Users with existing scripts that overwrite need to add the flag.

### Technical

- New exit code `3` (`WARN`) for `--warn-threshold` exceeded. `--exit-codes` table now has 11 codes.
- `core/timings.py` — lightweight `Timer` context manager (off by default, zero-cost no-op when disabled).
- `core/run_summary.py` — `RunSummary` + `PerRsidResult` dataclasses for `--run-summary-json`.
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
