# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
