# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

`aa_auto_sdr` is a shipped tool. The architectural rules below describe the as-built shape, not a forward-looking target. See `CHANGELOG.md` for release history.

## Mission

`aa_auto_sdr` is the Adobe Analytics counterpart to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr). It generates Solution Design Reference (SDR) documentation from an Adobe Analytics report suite and tracks how that SDR changes over time via snapshot diffing.

The two projects are sister tools that share **UX conventions** — CLI flags, env-var contract, profile layout, output format aliases, exit codes — so users moving between them feel at home. They do **not** share code, and they will not converge. Each repo installs independently, ships independently, and has no runtime, build-time, or development dependency on the other.

The architectural patterns called out below (SDK isolation, writer-protocol output layer, pure builder) exist because they are good design in their own right, not because they prepare for any package extraction. There is no shared-core roadmap.

## Stack & Toolchain (binding)

- **Python:** `>=3.14` (matches the sister project).
- **Package manager:** `uv`. All commands are `uv run …`.
- **Build backend:** `hatchling` with dynamic version sourced from `src/aa_auto_sdr/core/version.py`.
- **AA SDK:** [`aanalytics2`](https://github.com/pitchmuc/adobe-analytics-api-2.0) (PyPI: `aanalytics2`). This is the AA equivalent of `cjapy` in the sister project — wrapped in our own client module so the rest of the codebase never imports it directly.
- **Adobe Analytics API:** **2.0 only, READ-ONLY.** Two hard constraints, both non-negotiable:
  1. **No legacy 1.4 API.** Do not call, wrap, or fall back to it. Features that exist only in 1.4 (some classification import flows, legacy data warehouse) are out of scope. Enforcement is a meta-test (`tests/meta/test_no_legacy_1_4_paths.py`) that blocks 1.4-prefixed strings in `src/aa_auto_sdr/api/`. A typed exception class `UnsupportedByApi20` exists in `core/exceptions.py` for future raise sites; today, missing-in-2.0 surfaces are simply not implemented rather than raised at call time.
  2. **No write operations against AA, ever.** This tool reads. It never creates, updates, or deletes anything in a customer's Adobe Analytics environment — no segments, no calculated metrics, no classifications, no anything. The only methods called on the SDK handle are `getX` / list / describe / search / fetch shapes. Forbidden verb prefixes (informed by the actual `aanalytics2` write surface): `create|update|delete|put|patch|post|remove|import|save|write|share|send|resend|reprocess|commit|disable|enable|renew`. A meta-test (`tests/meta/test_read_only_aa.py`) scans `src/aa_auto_sdr/api/` for these patterns and fails the suite if found. (Local writes — snapshot files, output files, `~/.aa/orgs/` profiles — are unrelated to this rule and are fine.)
- **Auth:** Adobe OAuth Server-to-Server (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`). Same env-var contract as `cja_auto_sdr`. OAuth S2S is the only supported auth path. **Verified-minimum SCOPES for the read surface this tool exercises:** `openid,AdobeID,additional_info.projectedProductContext` (three scopes, no-space comma-separated — the canonical form per `docs/CONFIGURATION.md`). `read_organizations` and `additional_info.job_function` are recommended for fuller endpoint coverage but not empirically required for the current surface; add them if `--list-reportsuites` returns empty or `/dimensions` / `/metrics` return 403 despite a successful auth. Bootstrap is two-step: `aanalytics2.configure(**creds) → Login().getCompanyId() → Analytics(globalCompanyId)`. The integration must also be added to an Adobe Analytics Product Profile in Admin Console for any data to be visible.
- **Output deps:** `pandas`, `xlsxwriter`.

## CLI Conventions

Mirror the sister project so users moving between AA and CJA see the same surface. Two console entry points: `aa_auto_sdr` and `aa-auto-sdr`, both bound to `aa_auto_sdr.__main__:main`.

| Mode | Flag | Notes |
|------|------|-------|
| Single | `aa_auto_sdr <RSID>` | Generate SDR for one report suite |
| Batch | `--batch <RSID...>` | Generate SDRs for multiple report suites in one run |
| Discovery | `--list-reportsuites`, `--list-virtual-reportsuites` | Replaces CJA's `--list-dataviews`/`--list-connections` |
| Inspection | `--describe-reportsuite`, `--list-metrics <RSID>`, `--list-dimensions <RSID>`, `--list-segments <RSID>`, `--list-calculated-metrics <RSID>`, `--list-classification-datasets <RSID>` | |
| Diff | `--diff <source> <target>` | Snapshot comparison — version control for SDRs |
| Trending | `--trending-window <DURATION>`, `--compare-with-prev` | Drift / cross-snapshot rollup |
| Watch | `--watch --interval <DURATION>` | Foreground monitoring loop, NDJSON events |
| Quality | `--quality-report`, `--quality-policy`, `--fail-on-quality` | Severity-tagged audit gate |
| Config | `--profile`, `--profile-add`, `--config-status`, `--show-config` | Profiles in `~/.aa/orgs/<name>/` |

Format aliases (`excel`, `csv`, `json`, `html`, `markdown`, `all`, `reports`, `data`, `ci`) and shared flags (`--filter`, `--exclude`, `--sort`, `--limit`, `--output -`, `--output-dir`) match the CJA tool exactly.

Fast-path flags (no heavy imports — handle in `__main__.py` before pandas/aanalytics2 load): `--version`/`-V`, `--help`/`-h`, `--exit-codes`, `--explain-exit-code CODE`, `--completion {bash,zsh,fish}`.

See `docs/CLI_REFERENCE.md` for the full flag inventory and `AGENTS.md` for the agent-mode contract.

## Capability surface

Capabilities currently implemented:

- Single-report-suite and batch SDR generation (Excel, CSV, JSON, Markdown, HTML).
- Component coverage: dimensions (eVars/props/events), metrics, segments, calculated metrics, virtual report suites, classification datasets.
- Snapshot save + diff (versioned envelope, `git diff`-friendly, three-token resolver: paths / `<RSID>@<ts>` / `git:<ref>:<path>`).
- Discovery / inspection commands listed above.
- Profile-based multi-org auth.
- Parallel batch (`--workers`, `--fail-fast`), sampling (`--sample`, `--sample-seed`, `--sample-stratified`).
- Drift / trending windows (`--trending-window`, `--compare-with-prev`).
- Quality severity engine (`--quality-report`, `--quality-policy`, `--fail-on-quality` → exit 17).
- Inventory rollup (`--inventory-summary`).
- Watch / scheduled mode (`--watch`, `--interval`, `--watch-threshold`, NDJSON events on stdout).
- Resilience layer (retry-with-jitter, configurable via `--max-retries` / `--retry-base-delay` / `--retry-max-delay`; permanent VRS endpoint-shape errors fast-fail to a degraded, empty VRS section).
- Agent mode (`--agent-mode` preset: `--format json --output - --log-format json`).

Out of scope: API auto-tuning, circuit breakers, derived-field-only mode. Do not port from `cja_auto_sdr` without first asking.

## Concept Mapping: CJA → AA

When translating logic from `cja_auto_sdr`, swap concepts rather than copying code blindly:

| CJA concept | AA concept |
|-------------|------------|
| Data View | Report Suite (RSID) |
| Connection | (no direct equivalent — skip) |
| Dataset | (no direct equivalent — skip) |
| Derived Field | Classifications (closest analogue; not identical) |
| Components (metrics/dims/segments/CMs) | Same names, different SDK shapes |

`aanalytics2` returns different shapes than `cjapy` — normalize at the client boundary into our own dataclasses so the rest of the code is SDK-agnostic.

## Architectural rules (non-negotiable)

The on-disk module map is in `README.md` ("Project structure"); treat that as descriptive. The rules below are prescriptive — every change should respect them.

- **No monolithic orchestrator.** `sdr/builder.py` composes from `api/` outputs. If it grows past a comfortable read, split by component type, not by output format.
- **SDK isolation.** Only `api/client.py` imports `aanalytics2`. Everything downstream consumes our normalized models. Protects the codebase from SDK churn and keeps tests fast.
- **Writer protocol.** Output writers implement a single `Writer` protocol and self-register. Adding a format = one new file, no edits to a central dispatcher.
- **Pure builder.** `sdr/builder.py` takes data in, returns a document object. It does no I/O. Output is a separate step.
- **Lazy imports for heavy deps.** Defer `pandas`/`xlsxwriter`/`aanalytics2` imports until a command actually needs them. The fast path stays fast.
- **No 1.4 API and no AA writes.** Both invariants are enforced by meta-tests under `tests/meta/`.

## Snapshot / Version Control (load-bearing feature)

Snapshots are first-class, not an afterthought:

- Snapshot format is stable, human-readable JSON, versioned with a `schema` field (currently `aa-sdr-snapshot/v4`; see `docs/SNAPSHOT_DIFF.md` for the current schema and `CHANGELOG.md` for version history), and round-trip safe.
- Diffs are computed on normalized models, not on rendered output, so format changes don't create false diff noise.
- Snapshot files are friendly to `git diff` — sorted keys, stable ordering of components by ID.
- The diff command accepts filesystem paths, git refs, and snapshot store identifiers as inputs.

## Documentation conventions

- **Version anchors in prose are reserved for one of three cases:** (1) a hard system requirement (e.g. `Python 3.14+`); (2) back-compat behavior triggered by reading older artifacts (e.g. `v1 snapshots load with both keys defaulted to true`); (3) a deliberate behavior pivot whose old form may still be encountered. Everything else — "added in vX", "as of vY" — belongs in `CHANGELOG.md`, not in user-facing docs. Once a feature ships, it's a feature of the tool.
- `CHANGELOG.md` is the source of truth for *when*. The rest of the docs are the source of truth for *what*.
- Source-of-truth assignments for facts that recur across docs:
  - **Exit codes** → `src/aa_auto_sdr/core/exit_codes.py` (consumed by `--exit-codes`). Other docs link, don't duplicate.
  - **Env-var contract** → `docs/CONFIGURATION.md`. README/QUICKSTART teaser only.
  - **`--diff` token forms** → `docs/SNAPSHOT_DIFF.md`. CLI_REFERENCE one-line summary.
  - **Snapshot envelope schema** → `docs/SNAPSHOT_DIFF.md` with current `vN`. `CHANGELOG.md` for history.
  - **Output format aliases** → `docs/OUTPUT_FORMATS.md`.
  - **Logging events & frequency** → `docs/LOGGING_STYLE.md`.

## Common Commands

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
- If a feature exists in `cja_auto_sdr` and isn't already implemented here, do not port it without asking the user. The point of starting fresh was to leave behind organic complexity.
- `AGENTS.md` at the repo root is the machine-readable contract for unattended and agent-driven runs. Keep it in sync with CLI surface changes (new flags, new commands, exit-code additions).
