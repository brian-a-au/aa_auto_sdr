# Codebase audit — 2026-09-04

Baseline revision: `7fe9676`. Improvements prepared for patch release `1.21.13`.
Instructions reviewed: `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`.

## Review record

| Area | Review / findings | Status |
| --- | --- | --- |
| Entry points, CLI parser / dispatch | Fast paths intentionally avoid heavy imports. Modifier validation and exit-code precedence are supported contracts. Generate/batch have substantial option threading and repeated error handling. | Reviewed dispatch, option-resolution helpers, command paths, and tests; no wholesale dispatcher rewrite. |
| API client, auth, fetch, retries | SDK boundary normalizes ragged DataFrames, retries transient failures, preserves degraded status. Batch already preloads suite listing. VRS still lists the whole org per RSID. | Preserve normalizers/retry wrappers; shared VRS fetch needs freshness/failure semantics. |
| SDR builder / models | Sorting by ID supports stable snapshots. Thin auth mapper is a meaningful SDK boundary. | Retain. |
| Quality / cache / policy | Constant-return severity wrapper; redundant LOW branch. Cache key flattens component types and sorts away input order. | Simplified severity path; fixed type/order/separator cache collisions, reproduced against baseline. |
| Batch / workers / sampling | Duplicate exception mapping and output-size helpers. Stratified top-up scans sampled list for every input. | Consolidated outcome helpers and worker recording; replaced quadratic membership scan with a set. |
| Watch | Injectable clock/store/fetcher support deterministic loop tests. Publication differs from heartbeat emission. | Retain collaborators and separate predicates. |
| Snapshot / diff / retention / trending / git | Trending already streams adjacent snapshots; retention already slices. Suppressed diff sections retain underlying deltas. | Preserve compatibility; avoid changing suppression payloads. |
| CSV / Markdown / HTML / Excel | CSV/Markdown/HTML deep-copy each dataclass before read-only cell formatting. Separate atomic helpers have different permissions/symlink semantics. | Removed copies in CSV/Markdown/HTML; full file bytes unchanged in benchmark. Retained atomic-write contracts and Excel implementation. |
| Template Excel | Anchor matching, reserved rows, style/formula preservation are supported behavior. | Reviewed anchor resolution and all fill engines; retained template behavior. |
| Notion | Registry lock protects local writes; API block limits and pagination drive wrappers. Schema cache is global; repair does not invalidate it. | Reviewed block generation, pagination, registry/database operations, and maintenance handlers; no live writes. Cache freshness remains a follow-up. |
| Core utilities / credentials / logging | Redaction, filesystem permissions, credential precedence are load-bearing. | Reviewed precedence, redaction/filter/formatter paths, atomic I/O, summaries, timings, colors, and OS helpers; retained safety behavior. |
| Tests | Constructor echo tests; constant assertions; misleading empty-CSV/HTML-escaping assertions; default-list test supplies explicit lists. Git fixtures inherit global signing. | Removed 23 test functions; corrected 3 misleading tests and narrowed frozen-model exception assertions. Added 4 meaningful parametrized/scenario cases. |
| Dependencies / CI / scripts | All runtime dependencies have direct uses; optional deps have documented features. CI repeats Linux test/lint in release gate; check names may be protected externally. | Retain CI topology pending branch-protection decision. |

## Baseline and batches

- Baseline Ruff 0.16.4: lint and formatting pass (357 files).
- Baseline pytest: 99.57% coverage; one failed test and five fixture errors,
  all from inherited SSH commit signing in temporary Git repositories.
- Dependabot: GitHub read-only check found only PR #104, Ruff 0.16.4 →
  0.16.5, branch tip `4e34a9c`. Applied its exact lockfile patch locally.
- Disabled commit signing only in the three affected temporary-repository
  setups. Focused Git/resolver run: 27 passed. User Git configuration unchanged.

## Test-removal coverage map

Before deleting helpers/tests, searched source, tests, documentation, exports,
registrations, and configuration. Removed helpers were private implementation
functions; writer registration and public contracts are preserved.

| Removed test group | Remaining behavior coverage |
| --- | --- |
| Seven model constructor echoes (`tests/api/test_models.py`) | Fetch normalization tests, builder tests, document/snapshot round trips; retained frozen-model checks with `FrozenInstanceError`. |
| Six pipeline constructor/default echoes and three sampling-model echoes | `tests/pipeline/test_batch.py`, `test_batch_sampling.py`, worker tests, CLI summaries; retained immutability checks and fixed the default-list isolation test to actually use defaults. |
| Three writer-extension constants | Existing real file creation, filenames, extension-appending and output-format tests. |
| `BANNER_WIDTH == 60` | CLI batch summary tests exercise rendered banners; width itself is a cosmetic implementation choice. |
| CSV `asdict` call-count test | CSV nested-definition serialization, headers and row tests; benchmark verifies complete file equality and input immutability without requiring a specific implementation. |
| Severity-version prefix and constant-return severity helper tests | Cache version invalidation tests retained; new mixed-name audit tests actual LOW severity and gate failure. |

New quality-cache cases cover component movement between sections, changed
input order, and separator-bearing names/IDs. All three reproduced wrong
results on `7fe9676` and pass now. Cache JSON framing is a correctness change;
no cache speedup is claimed.

## Verification and measurements

Completed on macOS arm64, CPython 3.14.5:

- Full `uv run --no-sync pytest -q`: **2,346 tests, all passed**, **99.70%**
  coverage (90% required). Baseline signing failures resolved in fixtures.
- Ruff **0.16.5** lint and format checks: pass for `src/ tests/ scripts/`
  and the new benchmark (356 Python files including the benchmark).
- `uv lock --check --offline`: pass; version synchronization: pass.
- Wheel + sdist build: pass; packaged README links: pass for both artifacts.
- Fresh wheel installation into a temporary environment: pass. Both console
  entry points, version/help/exit-code output, SDK import, and all writer
  registrations work. Installation resolves current dependencies independently
  of the development lockfile; full tests used the locked environment.
- `git diff --check`: pass.
- Focused checks passed after each batch (Git fixtures; writers/sampling;
  batch/workers; quality/cache; retry and trending renderer).

The initial no-change benchmark comparison was approximately 1.0× for each
workload. Final timings are medians of seven alternating before/after runs:

| Synthetic workload | Before | After | Ratio |
| --- | ---: | ---: | ---: |
| Stratified sampling: 3,000 RSIDs, sample 1,501 | 21.488 ms | 0.939 ms | 22.89× |
| Stratified sampling: 30,000 RSIDs, sample 15,001 | 2,020.463 ms | 8.787 ms | 229.94× |
| CSV: 1,000 segments, 20 nested predicates each | 53.560 ms | 33.389 ms | 1.60× |
| Markdown: same document | 41.164 ms | 21.975 ms | 1.87× |
| HTML: same document | 58.540 ms | 39.014 ms | 1.50× |

Sampling preserves input/seed behavior and changes the top-up membership
work from O(N × sample size) to O(N + sample size), with a temporary set.
Text writers read normalized dataclass fields directly instead of deep-copying
nested JSON before read-only formatting. Benchmarks time complete writes,
including local atomic replacement, on warm temporary storage. These are not
end-to-end API speedups and do not measure peak memory.

Reproducible synthetic benchmark:
`uv run python benchmarks/audit_hotpaths.py --baseline-ref 7fe9676`.
It compares seeded sample output and full CSV/Markdown/HTML file bytes, checks
input immutability, and alternates before/after timing order. It excludes
imports, fixture construction, and live API latency.

## Retained candidates and limitations

- **Decision: sharing org-wide VRS responses.** Batch/stats/inventory still
  fetch all VRS per RSID and then filter. Sharing could reduce requests, but
  needs an explicit freshness boundary (batch versus watch cycle), treatment
  of failures, and concurrent refresh semantics. No request savings claimed.
- **Decision: external compatibility.** `STATS_STDOUT_FORMATS` is an unused
  but explicitly exported constant. `UnsupportedByApi20` is reserved and
  documented in repository instructions. Neither was removed.
- **Decision: CI required checks.** Release-gate repeats Linux tests/lint
  already run elsewhere. Collapsing jobs can break branch-protection check
  names; CI topology was preserved. No GitHub settings were changed.
- **Further engineering review:** stats/inventory duplicate resolution/count
  assembly; single/batch CLI option threading remains large. Consolidation
  should preserve their distinct errors, stdout conventions, and logging.
- **Unresolved state-lifetime question:** Notion schema cache refresh after
  repair/external schema edits and singleton writer configuration across
  embedded concurrent runs deserve focused follow-up. Live Notion behavior
  was not exercised.
- Template anchor rules, 50-row append cap, snapshot schema compatibility,
  fetch degradation, and atomic permission/symlink differences are supported
  behavior and were retained. Suppressed diff sections keep underlying deltas
  for consumers; skipping their comparison would change the JSON payload.
- No runtime dependency was removed: SDK/pandas, requests, Excel libraries,
  and optional dotenv/completion/Notion dependencies have direct consumers.
- Includes the Ruff 0.16.5 dependency update from Dependabot PR #104.
  No live Adobe or Notion application writes were performed.

Review covered every major subsystem listed above, with deeper inspection of
changed paths and selected tests. The inventory contains 107 source modules
and 228 test modules after cleanup. This is a subsystem review, not a claim
that every line or every test was individually audited. Live Adobe/Notion
calls and Linux/Windows execution are outside local verification.
