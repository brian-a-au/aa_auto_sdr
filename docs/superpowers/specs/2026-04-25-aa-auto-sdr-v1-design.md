# aa_auto_sdr — v1.0.0 Design Spec

**Date:** 2026-04-25
**Status:** Approved (brainstorming phase complete)
**Repo:** `/Users/bau/DEV/aa_auto_sdr`
**Sister project (UX reference, not a code dependency):** [`brian-a-au/cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr)

---

## 0. Non-goals (for v1.0.0 and beyond)

- **No code sharing with `cja_auto_sdr`.** No shared library, no extracted package, no cross-imports. The two repos are independent installs and will stay that way.
- **No CJA features in this tool.** No CJA data view support, no cross-product diffing, no unified mode.
- **No build-time or dev-time dependency between the repos.** Each can be cloned, installed, and developed in full isolation.
- **Convention mirroring is a UX choice, not an architectural commitment.** Where AA-specific concepts (classifications, eVar/prop/event taxonomy, virtual report suites) require divergence from CJA's surface, divergence wins. The design optimizes for AA users, not for symmetry.
- **No legacy 1.4 API support.** Adobe Analytics API 2.0 only. Where a needed component is not reachable through 2.0, raise a typed `UnsupportedByApi20` error rather than degrading to 1.4.
- **No quality / validation engine in v1.0.0.** Severity classification, dashboard sheets, and quality policy logic are out of scope; defer to a later release.
- **No org-wide reports, drift trending, circuit breakers, or API auto-tuning.** These were learned features in `cja_auto_sdr`; do not port speculatively.

Acceptance of duplication with `cja_auto_sdr` is explicit. Snapshot/diff format, output writers, CLI scaffolding, credential resolution, exit-code system, version-sync script, and CI workflows will all exist in parallel with their CJA equivalents. Drift between the two over time is acceptable; convergence is not a goal.

---

## 1. System overview

`aa_auto_sdr` is a CLI tool that connects to one Adobe Analytics organization via OAuth Server-to-Server (API 2.0 only), fetches the components of a report suite (dimensions, metrics, segments, calculated metrics, virtual report suites, classifications), normalizes them into SDK-agnostic dataclasses, assembles an SDR (Solution Design Reference) document, and renders it in five output formats (Excel, CSV, JSON, HTML, Markdown). It also persists snapshots of the normalized SDR model to disk so changes between two points in time can be diffed — this "version control of SDR" capability is a first-class feature, not an add-on.

The tool is a sister project to `cja_auto_sdr`. CLI conventions, env-var contract, profile layout, format aliases, and exit-code semantics mirror that project so users running both tools see the same surface. Internals are AA-specific and do not share code with CJA.

---

## 2. Package architecture

```text
src/aa_auto_sdr/
├── __init__.py              # Lazy forwarding (__version__, main)
├── __main__.py              # Fast-path entry — handles --version/--help/--exit-codes/--completion in <100ms
│
├── api/                     # AA 2.0 SDK isolation
│   ├── client.py            # Wraps aanalytics2.Analytics; forbids 1.4 endpoints; raises UnsupportedByApi20
│   ├── auth.py              # OAuth S2S credential loading (env or profile)
│   ├── models.py            # Normalized dataclasses: ReportSuite, Dimension, Metric, Segment, CalculatedMetric, VirtualReportSuite, Classification
│   ├── fetch.py             # Per-component fetchers — return normalized models
│   └── resilience.py        # Retry-with-jitter only. No circuit breaker, no auto-tuning.
│
├── cli/                     # argparse + dispatch
│   ├── parser.py            # All argument definitions in one place
│   ├── main.py              # Thin dispatcher
│   └── commands/
│       ├── generate.py      # Single-RSID and --batch
│       ├── discovery.py     # --list-reportsuites, --list-virtual-reportsuites
│       ├── inspect.py       # --describe-reportsuite, --list-metrics/dimensions/segments/calculated-metrics
│       ├── diff.py          # --diff
│       └── config.py        # --config, --show-config, --profile-add, --profile, --stats
│
├── core/                    # Cross-cutting utilities
│   ├── version.py           # Single source of truth for __version__
│   ├── constants.py         # Defaults (worker counts, paths, banner widths)
│   ├── config.py            # SDR generation config dataclass
│   ├── credentials.py       # Env + profile + .env + config.json resolution
│   ├── profiles.py          # ~/.aa/orgs/<name>/ profile CRUD
│   ├── exceptions.py        # Typed exception hierarchy
│   ├── exit_codes.py        # Exit code enum + --explain-exit-code
│   ├── logging.py           # Structured logging
│   └── json_io.py           # Atomic JSON read/write
│
├── sdr/                     # SDR assembly
│   ├── builder.py           # Pure: normalized models → SdrDocument. Target <500 lines.
│   └── document.py          # SdrDocument dataclass
│
├── pipeline/                # Run coordination
│   ├── single.py            # Single-RSID wrapper
│   ├── batch.py             # Multi-RSID, sequential, continue-on-error
│   └── models.py            # RunResult, BatchResult
│
├── snapshot/                # Version control of SDR
│   ├── store.py             # Save/load. Path: ~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-timestamp>.json
│   ├── schema.py            # Snapshot JSON schema v1, with version field for forward-compat
│   ├── comparator.py        # Diff on normalized models, not rendered output
│   ├── git.py               # Git-ref resolution (HEAD~1, branch names, etc.)
│   └── resolver.py          # Resolves <RSID>@<ts>, file paths, git refs to a snapshot blob
│
└── output/                  # Format writers
    ├── protocols.py         # Writer protocol
    ├── registry.py          # Format → Writer registry; format aliases (all/reports/data/ci)
    └── writers/
        ├── excel.py         # Multi-sheet, frozen headers, autofilter, basic conditional formatting
        ├── csv.py
        ├── json.py
        ├── html.py
        └── markdown.py
```

### Hard architectural rules

- **SDK isolation:** only `api/client.py` and `api/fetch.py` import `aanalytics2`. Anything else doing so is a bug. Tests assert this with a meta-test that greps `src/aa_auto_sdr/` for forbidden imports outside `api/`.
- **No 1.4 paths:** a meta-test scans `api/` source for any reference to legacy 1.4 endpoint paths and fails the suite if found.
- **Builder purity:** `sdr/builder.py` does no I/O. Fetch is a separate step; render is a separate step. Builder takes normalized models, returns an `SdrDocument`. Target file size <500 lines; if it grows, split by component type, not by output format.
- **Writer protocol:** output writers self-register via the `Writer` protocol. Adding a format = one new file under `output/writers/`, no edits to a central dispatcher.
- **Lazy heavy imports:** `pandas`, `xlsxwriter`, `aanalytics2` are imported only when a code path actually needs them. The fast-path entry (`__main__.py`) must complete `--version`/`--help`/`--exit-codes`/`--completion` in <100ms wall time.

---

## 3. Data flow

```text
CLI invocation
  └─→ cli/parser.py parses args
      └─→ cli/main.py dispatches by mode
          ├─→ generate: pipeline/single.py or pipeline/batch.py
          │       └─→ api/client.py authenticates
          │           └─→ api/fetch.py pulls components → api/models.py dataclasses
          │               └─→ sdr/builder.py composes SdrDocument
          │                   ├─→ output/registry.py routes to writer(s) → file(s)
          │                   └─→ snapshot/store.py persists normalized SdrDocument as JSON
          │
          ├─→ discovery/inspect: api/client.py → api/fetch.py → output writer (json/csv/console)
          │
          └─→ diff: snapshot/resolver.py → snapshot/comparator.py → output/writers/*
```

### Boundary invariants

1. **`SdrDocument` is the boundary.** Builder produces it; output and snapshot consume it. Snapshot stores the same shape Builder produces — not the rendered result.
2. **Diffs run on `SdrDocument`s, not on rendered files.** Renaming a column in Excel does not create a false diff.
3. **Component identity is by ID, never by display name.** A name change is a *modification*, not an `add` + `remove`.

---

## 4. Snapshot and diff model

### Storage

- Default path: `~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-8601-timestamp>.json`
- File is JSON, sorted keys, stable component ordering by ID — git-diff-friendly out of the box.
- Header on every file:

  ```json
  {
    "schema": "aa-sdr-snapshot/v1",
    "rsid": "...",
    "captured_at": "2026-04-25T17:29:01Z",
    "tool_version": "1.0.0",
    "components": { ... }
  }
  ```

  The `schema` field enables future migrations; loaders reject unknown major versions with `SnapshotSchemaError`.

### Resolution (`--diff <a> <b>`)

`snapshot/resolver.py` accepts any of:

- A filesystem path to a snapshot file.
- `<RSID>@<timestamp>` shorthand (resolves against the active profile's snapshot directory).
- `<RSID>@latest` and `<RSID>@previous` aliases.
- A git ref (`HEAD`, `HEAD~1`, branch name) — resolves the snapshot file at that ref in the user's current git repo.

### Diff semantics

`snapshot/comparator.py` produces, per component type:

- `added` — components present in target but not source
- `removed` — components present in source but not target
- `modified` — components present in both, with field-level deltas
- `unchanged_count` — integer, no detail

Output formats: console (grouped, color-coded), JSON (machine-readable), Markdown (PR-comment-friendly).

---

## 5. CLI surface (v1.0.0)

```text
# Generation
aa_auto_sdr <RSID>                              # Single, default Excel
aa_auto_sdr <RSID> --format <fmt>               # excel|csv|json|html|markdown|all|reports|data|ci
aa_auto_sdr <RSID> --output-dir <dir>
aa_auto_sdr <RSID> --output -                   # Stdout (json/csv/markdown only)
aa_auto_sdr --batch <RSID> [<RSID>...]          # Multi-RSID

# Discovery
aa_auto_sdr --list-reportsuites [--filter] [--exclude] [--limit] [--sort] [--format] [--output]
aa_auto_sdr --list-virtual-reportsuites [...same options...]

# Inspection
aa_auto_sdr --describe-reportsuite <RSID>
aa_auto_sdr --list-metrics <RSID> [filter/exclude/sort/limit/format/output]
aa_auto_sdr --list-dimensions <RSID> [...]
aa_auto_sdr --list-segments <RSID> [...]
aa_auto_sdr --list-calculated-metrics <RSID> [...]

# Diff
aa_auto_sdr --diff <a> <b> [--format console|json|markdown]

# Config / profiles
aa_auto_sdr --config
aa_auto_sdr --show-config
aa_auto_sdr --profile-add <name>     # interactive
aa_auto_sdr --profile <name> ...     # use named profile
aa_auto_sdr --stats

# Fast-path (no heavy imports; <100ms)
aa_auto_sdr --version | -V
aa_auto_sdr --help | -h
aa_auto_sdr --exit-codes
aa_auto_sdr --explain-exit-code <CODE>
aa_auto_sdr --completion {bash,zsh,fish}
```

### Format aliases

| Alias     | Resolves to                                        |
|-----------|----------------------------------------------------|
| `excel`   | `.xlsx` workbook (default)                         |
| `csv`     | CSV file(s)                                        |
| `json`    | JSON file                                          |
| `html`    | HTML report                                        |
| `markdown`| Markdown file                                      |
| `all`     | All five formats + console summary                 |
| `reports` | excel + markdown                                   |
| `data`    | csv + json                                         |
| `ci`      | json + markdown                                    |

---

## 5.5. Authentication and credentials

Mirrors `cja_auto_sdr`. All four sources load the same OAuth S2S fields: `org_id`, `client_id`, `secret`, `scopes`, optional `sandbox`.

| Source                                  | Format                                           | When to use                                         |
|-----------------------------------------|--------------------------------------------------|-----------------------------------------------------|
| Profile                                 | `~/.aa/orgs/<name>/config.json` via `--profile-add` | Multi-org users; default for daily use              |
| Environment variables                   | `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`, `SANDBOX`, `LOG_LEVEL` | CI, scripts, container deploys                      |
| `.env` file                             | `KEY=value` lines via optional `python-dotenv`   | Local dev — same vars as above                      |
| `config.json` in working directory      | JSON with `org_id`, `client_id`, `secret`, `scopes`, `sandbox` | Project-scoped credentials in a repo (gitignored)   |

### Resolution precedence (highest wins)

1. `--profile <name>` flag (or `AA_PROFILE` env var pointing at a named profile)
2. Environment variables already in shell
3. `.env` file in working directory (only if `python-dotenv` installed)
4. `config.json` in working directory

`core/credentials.py` walks this chain in order, returns the first complete credential set, and emits a diagnostic line showing which source was used.

`python-dotenv` and `argcomplete` stay optional dependencies so the base install is lean. Env-var names are identical to `cja_auto_sdr` (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`, `SANDBOX`) so users running both tools share one `.env`. The default-profile env var is `AA_PROFILE` (CJA's is `CJA_PROFILE`). `LOG_LEVEL` is honored.

---

## 6. Error handling and exit codes

### Typed exception hierarchy (`core/exceptions.py`)

```text
AaAutoSdrError                    # Base
├── ConfigError                   # Bad config / missing creds
├── AuthError                     # OAuth failure
├── ApiError                      # Network / API error
│   └── UnsupportedByApi20        # Feature only available in 1.4 — explicit
├── ReportSuiteNotFoundError
├── SnapshotError
│   ├── SnapshotResolveError
│   └── SnapshotSchemaError
└── OutputError
```

### Exit codes (mirror `cja_auto_sdr` semantics)

| Code   | Meaning                              |
|--------|--------------------------------------|
| 0      | Success                              |
| 1      | Generic error                        |
| 2      | Argument / usage error (argparse)    |
| 10     | Config error                         |
| 11     | Auth error                           |
| 12     | API error                            |
| 13     | Resource not found                   |
| 14     | Snapshot error                       |
| 15     | Output error                         |
| 64+    | Reserved                             |

`--exit-codes` lists every code; `--explain-exit-code <N>` prints a one-paragraph explanation and remediation hint.

### Machine-readable errors

When `--output -` or `--format json` is in effect and an error occurs, write a JSON error envelope to stderr:

```json
{"error": {"code": 11, "type": "AuthError", "message": "...", "hint": "..."}}
```

Stdout remains valid for downstream tools that expect JSON or empty output on failure.

---

## 7. Testing strategy

### Framework

- `pytest`, `pytest-cov`, `pytest-xdist`. Test runner config in `pytest.ini`.
- Markers: `unit` (default, auto-applied), `integration`, `e2e`, `smoke`.
- Auto-classification via `conftest.py` from a `category_rules.py` map.

### Coverage gate

- **90%** on the unit slice for v1.0.0 (`--cov-fail-under=90`). Lower than CJA's 95% to leave headroom; tighten in v1.1+.
- Coverage measured on the unit slice only; integration and e2e tests do not contribute.

### Mock pattern

- Patch `aa_auto_sdr.api.client.aanalytics2` and `aa_auto_sdr.api.fetch.aanalytics2`.
- Never patch the SDK at the import root — encourages bad test hygiene.

### Test categories

| Category    | Scope                                                                 | Speed target |
|-------------|-----------------------------------------------------------------------|--------------|
| `unit`      | `builder`, `comparator`, `resolver`, writers, parser — no network     | <30s total   |
| `integration` | `pipeline/` end-to-end with mocked client                          | <60s         |
| `smoke`     | Subprocess invocation of CLI; fast-path flag verification             | <10s         |
| `e2e`       | Real-API tests, gated by env var; not run in unit CI                  | manual       |

### Snapshot fixture corpus

A committed JSON corpus under `tests/fixtures/snapshots/` provides a representative report suite shape, enabling fast end-to-end tests of `builder → writer → diff` without any AA mocks.

### Meta-tests

- **No SDK leakage:** scans `src/aa_auto_sdr/` for `import aanalytics2` outside `api/`. Fails on match.
- **No 1.4 paths:** scans `api/` source for known 1.4 endpoint substrings. Fails on match.
- **Exit-code completeness:** asserts every value in the `ExitCode` enum has both an `--exit-codes` row and an `--explain-exit-code` entry.

---

## 8. Release infrastructure (the v1.0.0 cut)

### CI workflows (`.github/workflows/`)

| Workflow            | Purpose                                                                                                  |
|---------------------|----------------------------------------------------------------------------------------------------------|
| `tests.yml`         | Unit + integration + smoke tests; coverage gate; macOS + Linux + Windows smoke matrix                    |
| `lint.yml`          | `ruff check`, `ruff format --check`, `actionlint`, `shellcheck`                                          |
| `version-sync.yml`  | `scripts/check_version_sync.py` validates version consistency across all places it appears               |
| `release-gate.yml`  | Pre-tag checks: tests pass, lint clean, `CHANGELOG.md` has entry for tag version, README/docs current   |
| `publish.yml`       | On tag push, build + upload to PyPI via trusted publishing (OIDC, no stored API tokens)                  |

### Tooling

- **Ruff:** `target-version = "py314"`, `line-length = 120`. Rule set comparable to `cja_auto_sdr`'s 41-rule profile.
- **Build backend:** `hatchling`, dynamic version sourced from `src/aa_auto_sdr/core/version.py`.
- **Entry points:** `aa_auto_sdr` and `aa-auto-sdr` (both bound to `aa_auto_sdr.__main__:main`).

### Version sync

Canonical source: `src/aa_auto_sdr/core/version.py`. `scripts/check_version_sync.py` validates the string appears identically in:

1. `src/aa_auto_sdr/core/version.py` (canonical)
2. `pyproject.toml` (dynamic, automatic — script asserts the dynamic config is wired correctly)
3. `CHANGELOG.md` (most recent `## [x.y.z]` heading)
4. `README.md` (badge or version line)
5. `CLAUDE.md` (if present)

### Documentation

- **`README.md`** — install, auth setup, every command with example, output samples, troubleshooting.
- **`CHANGELOG.md`** — Keep-a-Changelog format, entries from v0.1 forward.
- **`docs/`** — markdown only at v1.0.0 (no docs site):
  - `QUICKSTART.md`
  - `CLI_REFERENCE.md`
  - `CONFIGURATION.md`
  - `SNAPSHOT_DIFF.md`
  - `OUTPUT_FORMATS.md`

### Distribution

- PyPI package name: `aa-auto-sdr`.
- Trusted publishing via GitHub Actions OIDC. No PyPI tokens stored in repo or org secrets.
- Smoke verification: `pip install aa-auto-sdr` from a clean machine produces a working `aa_auto_sdr --version`.

---

## 9. Milestone roadmap

Each cut is independently usable. Each cut gets its own implementation plan via `superpowers:writing-plans` when its turn comes — one plan per milestone keeps each one tractable.

| Cut       | Adds                                                                                                       | Definition of done                                                                                                  |
|-----------|------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| **v0.1**  | Project skeleton; OAuth S2S auth (env + profile); `api/client.py`; single-RSID generation; JSON + Excel output; `--profile-add` / `--profile`. | `aa_auto_sdr <RSID>` produces a correct Excel and JSON for a known RS. Unit coverage ≥ 70% (relaxed for spike phase). |
| **v0.3**  | All five output formats wired through `Writer` protocol; format aliases (`all`, `reports`, `data`, `ci`); discovery commands (`--list-reportsuites`, `--list-virtual-reportsuites`); inspect commands (`--list-metrics`/`-dimensions`/`-segments`/`-calculated-metrics`). | All output formats validated against fixture corpus; discovery and inspect commands functional with `--filter`/`--sort`/`--limit`. |
| **v0.5**  | Batch generation (`--batch`, sequential, continue-on-error); per-RSID result reporting; structured logging.                              | Batch run across N RSIDs produces N output sets and one batch summary; partial failure does not abort the run.       |
| **v0.7**  | Snapshot store + schema v1; `--diff`; resolver (path, `<RSID>@ts`, git ref); diff renderers (console / JSON / Markdown). | `--diff` between two snapshots produces correct add/remove/modify report; git-ref resolution works in a real repo.   |
| **v0.9**  | Release-gate hardening: full ruff config; `core/exit_codes.py` + `--explain-exit-code`; `--completion`; `core/exceptions.py` complete; version-sync script; `CHANGELOG.md`; complete `README.md` + `docs/`; full CI matrix. | All CI workflows green; release-gate dry run passes; coverage gate raised to 90%.                                    |
| **v1.0.0**| Tag, build, PyPI publish via trusted publishing; sample outputs in `sample_outputs/`; final README polish.                           | Package installable via `pip install aa-auto-sdr` from a clean machine; smoke test passes; v1.0.0 entry in CHANGELOG. |

### Out-of-band work items

- **`aanalytics2` shape spike** — before v0.1, spend 2–3 hours fetching dimensions, metrics, segments, calculated metrics, classifications, and VRS through `aanalytics2` against a real RS to confirm the normalized model shapes in `api/models.py`. If classifications coverage in API 2.0 is partial, decide explicitly whether v1.0.0 ships best-effort classifications with `UnsupportedByApi20` for gaps, or whether classifications slips to v1.1.
- **Diagnostics wordlist** — once code lands, add a `.cspell.json` listing project-specific terms (`aanalytics`, `cjapy`, `RSID`, `xlsxwriter`, `pytest`) so editor diagnostics are quiet.

---

## 10. Open decisions deferred from this spec

These are tactical and do not block plan creation. They get resolved during implementation:

- **Classifications coverage extent in v0.1.** The `aanalytics2` spike answers this.
- **Worker pool for `--batch`.** Sequential in v0.5; add parallelism only if real-world runtimes justify it.
- **HTML output template.** Single-file standalone HTML with inline CSS, or templated. Decide during v0.3.
- **`--stats` content.** Mirror CJA's `--stats` if it's still useful by v0.9; otherwise drop.

---

## 11. References

- Sister project (UX reference, not a code dependency): <https://github.com/brian-a-au/cja_auto_sdr>
- Adobe Analytics API 2.0 SDK: <https://github.com/pitchmuc/adobe-analytics-api-2.0>
- Project root `CLAUDE.md` — operating notes for future Claude sessions; tracks current state as code lands.
