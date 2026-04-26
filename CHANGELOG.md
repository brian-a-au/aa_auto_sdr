# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
