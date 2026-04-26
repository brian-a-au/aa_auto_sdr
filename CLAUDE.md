# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Greenfield. The repository is initialized with no source yet. This file captures the design intent so the first implementation pass stays aligned with the project's goals; update it to reflect reality as code lands.

## Mission

`aa_auto_sdr` is the Adobe Analytics counterpart to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr). It generates Solution Design Reference (SDR) documentation from an Adobe Analytics report suite and tracks how that SDR changes over time via snapshot diffing.

The two projects are sister tools that share **UX conventions** — CLI flags, env-var contract, profile layout, output format aliases, exit codes — so users moving between them feel at home. They do **not** share code, and they will not converge. Each repo installs independently, ships independently, and has no runtime, build-time, or development dependency on the other.

The architectural patterns called out below (SDK isolation, writer-protocol output layer, pure builder) exist because they are good design in their own right, not because they prepare for any package extraction. There is no shared-core roadmap.

## Stack & Toolchain (binding)

- **Python:** `>=3.14` (matches the sister project — Python 3.14 exists and is correct).
- **Package manager:** `uv`. All commands are `uv run …`.
- **Build backend:** `hatchling` with dynamic version sourced from `src/aa_auto_sdr/core/version.py`.
- **AA SDK:** [`aanalytics2`](https://github.com/pitchmuc/adobe-analytics-api-2.0) (PyPI: `aanalytics2`). This is the AA equivalent of `cjapy` in the sister project — wrap it in our own client module so the rest of the codebase never imports it directly.
- **Adobe Analytics API:** **2.0 only.** Do not call, wrap, or fall back to the legacy 1.4 API under any circumstance. If `aanalytics2` exposes a 1.4 path, it is off-limits — pin SDK calls to 2.0 endpoints and document the constraint in `api/client.py`. Features that exist only in 1.4 (e.g. some classification import flows, legacy data warehouse) are out of scope; surface a clear error rather than degrading to 1.4.
- **Auth:** Adobe OAuth Server-to-Server (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`). Same env-var contract as `cja_auto_sdr`. JWT auth via `aanalytics2` is legacy — prefer OAuth S2S.
- **Output deps:** `pandas`, `xlsxwriter`. Avoid scipy/clustering at the start.

## CLI Conventions

Mirror the sister project so users moving between AA and CJA see the same surface. Two console entry points: `aa_auto_sdr` and `aa-auto-sdr`, both bound to `aa_auto_sdr.__main__:main`.

| Mode | Flag | Notes |
|------|------|-------|
| Single | `aa_auto_sdr <RSID>` | Generate SDR for one report suite |
| Batch | `--batch <RSID...>` | Generate SDRs for multiple report suites in one run |
| Discovery | `--list-reportsuites`, `--list-virtual-reportsuites` | Replaces CJA's `--list-dataviews`/`--list-connections` |
| Inspection | `--describe-reportsuite`, `--list-metrics <RSID>`, `--list-dimensions <RSID>`, `--list-segments <RSID>`, `--list-calculated-metrics <RSID>` | |
| Diff | `--diff <source> <target>` | Snapshot comparison — version control for SDRs |
| Config | `--config`, `--show-config`, `--profile`, `--profile-add` | Profiles in `~/.aa/orgs/<name>/` |

Format aliases (`excel`, `csv`, `json`, `html`, `markdown`, `all`, `reports`, `data`, `ci`) and shared flags (`--filter`, `--exclude`, `--sort`, `--limit`, `--output -`, `--output-dir`) match the CJA tool exactly.

Fast-path flags (no heavy imports — handle in `__main__.py` before pandas/aanalytics2 load): `--version`/`-V`, `--help`/`-h`, `--exit-codes`, `--explain-exit-code CODE`, `--completion {bash,zsh,fish}`.

## Initial Scope (v0.x)

**In scope from day one:**

1. Single-report-suite SDR generation (Excel + CSV + JSON + Markdown + HTML).
2. Batch SDR generation across multiple report suites (`--batch`). Sequential first; add a worker pool only if real-world runtimes justify it.
3. Component coverage: dimensions (eVars/props/events), metrics, segments, calculated metrics, virtual report suites, classifications.
4. Snapshot save + diff (the "version control of SDR" requirement — this is non-negotiable for v1). Batch mode must produce one snapshot per RSID so diffs work per-suite.
5. Discovery and inspection commands listed above.
6. Profile-based multi-org auth.

**Deliberately out of scope until later:** org-wide analysis, drift/trending windows, validation/quality severity engine, API auto-tuning, circuit breakers, derived-field/inventory-only modes. The CJA tool grew these over time; do not port them speculatively.

## Concept Mapping: CJA → AA

When translating logic from `cja_auto_sdr`, swap concepts rather than copying code blindly:

| CJA concept | AA concept |
|-------------|------------|
| Data View | Report Suite (RSID) |
| Connection | (no direct equivalent — skip) |
| Dataset | (no direct equivalent — skip) |
| Derived Field | Classifications (closest analogue; not identical) |
| Components (metrics/dims/segments/CMs) | Same names, different SDK shapes |

`aanalytics2` returns different shapes than `cjapy` — normalize at the client boundary into our own dataclasses so the rest of the code is SDK-agnostic. This is the single biggest architectural improvement to get right.

**API 2.0 enforcement:** the client wrapper is also where the 2.0-only constraint is enforced. If a needed component isn't reachable through the 2.0 API, raise a typed error (e.g. `UnsupportedByApi20`) — never silently fall through to a 1.4 endpoint. Tests should assert no 1.4 paths are taken.

## Architecture Targets (improvements over cja_auto_sdr)

The sister project has a ~7K-line `generator.py` that grew organically. Avoid that here. Target structure:

```
src/aa_auto_sdr/
├── __main__.py          # Fast-path entry (sub-100ms for --version/--help)
├── api/                 # aanalytics2 wrapper, auth, retry
│   ├── client.py        # Thin facade over aanalytics2.Analytics
│   ├── models.py        # Normalized dataclasses (ReportSuite, Dimension, Metric, …)
│   └── resilience.py    # Retry-with-jitter only at first; no circuit breaker yet
├── cli/                 # argparse + command dispatch
│   ├── parser.py
│   ├── commands/        # One module per command — no mega-dispatcher
│   └── main.py
├── core/                # Config, profiles, credentials, version, exceptions, exit codes
├── sdr/                 # SDR assembly — the orchestrator that replaces generator.py
│   ├── builder.py       # Pure: takes normalized models → SDR document
│   └── document.py      # SDR document data model
├── pipeline/            # Batch coordination
│   ├── single.py        # Single-RSID wrapper around builder
│   ├── batch.py         # Multi-RSID runner; continue-on-error, per-RSID result
│   └── models.py        # Run/result models
├── snapshot/            # Save/load + diff (replaces CJA's `diff/`)
│   ├── store.py
│   ├── comparator.py
│   └── git.py
└── output/              # Format writers behind a Writer protocol
    ├── protocols.py
    ├── registry.py
    └── writers/         # excel.py, csv.py, json.py, html.py, markdown.py
```

**Non-negotiable architectural rules:**

- **No monolithic orchestrator.** `sdr/builder.py` should compose from `api/` outputs and stay under ~500 lines. If it grows, split by component type, not by output format.
- **SDK isolation.** Only `api/client.py` imports `aanalytics2`. Everything downstream consumes our normalized models. This protects the codebase from SDK churn and keeps tests fast — not a shared-core enabler.
- **Writer protocol.** Output writers implement a single `Writer` protocol and self-register. Adding a format = one new file, no edits to a central dispatcher.
- **Pure builder.** `sdr/builder.py` takes data in, returns a document object. It does no I/O. Output is a separate step.
- **Lazy imports for heavy deps.** Defer `pandas`/`xlsxwriter`/`aanalytics2` imports until a command actually needs them. The fast path must stay fast.

## Snapshot / Version Control (load-bearing feature)

Snapshots are first-class, not an afterthought. Design constraints:

- Snapshot format must be stable and human-readable (JSON), versioned with a schema field, and round-trip safe.
- Diffs are computed on normalized models, not on rendered output, so format changes don't create false diff noise.
- Snapshot files should be friendly to `git diff` — sort keys, stable ordering of components by ID.
- The diff command should support filesystem paths, git refs, and snapshot store identifiers as inputs.

## Common Commands (once implemented)

```bash
uv sync                                  # Install
uv run pytest tests/                     # Test
uv run pytest tests/ -x -q               # Fast-fail
uv run ruff check src/ tests/            # Lint
uv run ruff format src/ tests/           # Format
uv run aa_auto_sdr <RSID>                # Generate SDR for one report suite
uv run aa_auto_sdr --batch <RSID...>     # Generate SDRs for multiple report suites
uv run aa_auto_sdr --diff <a> <b>        # Compare snapshots
```

## When in Doubt

- Reference `cja_auto_sdr` for CLI flag names, env-var contract, output format aliases, profile layout, and exit-code conventions — divergence from those is a regression for users who use both tools.
- Reference `aanalytics2` documentation (https://github.com/pitchmuc/adobe-analytics-api-2.0) for SDK shapes — but never let those shapes leak past `api/`.
- If a feature exists in `cja_auto_sdr` and it isn't on the "Initial Scope" list above, do not port it without asking the user. The point of starting fresh is to leave behind organic complexity.
