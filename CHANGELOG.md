# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
