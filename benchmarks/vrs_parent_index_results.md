# Invocation-local VRS parent index

U3 indexes the successful organization-wide VRS enumeration once at its existing
invocation ownership boundary. Parent buckets reference retained rows; only
selected rows are deep-copied for consumers. The complete index and diagnostic
counts publish together through the existing single-flight Future. Ordinary
string parents, missing/None parents and float NaN are indexed. Other parent
values or non-plain-dict rows retain the original scan, preserving its errors
outside the SDK-fetch degradation handler. Standalone calls remain scans.

This is an offline CPU optimization, with identical SDK arguments and retry
budgets. Both variants enumerate VRS once per command. No HTTP savings or live
Adobe latency improvement is claimed.

Baseline: `b851874fed05708502fcff217760a21363027314`. Candidate source digest:
`8814a32fd6a73f6b035736dd75c729485be330120c4823b6829c9c13dbbb54a7`.
The identical lock digest is
`3e0275f6d274eaf453c93d58e66de718d1263afa9b4c3fbed91a0b7181c568b7`.
Python 3.14.0 on macOS 26.6.2 arm64; aanalytics2 0.5.5.post2,
pandas 3.0.6, numpy 2.4.4, openpyxl 3.1.5, xlsxwriter 3.2.9.
Raw paired samples, platform, dependencies and source identities are retained in
[vrs_parent_index_results.json](vrs_parent_index_results.json).

The existing runner warms the complete stats command once, then measures seven
alternating baseline/candidate wall-time pairs without tracemalloc. One separate
allocation sample per variant records traced peak and process peak RSS. Fixture
construction/imports are outside the warm operation; stub credential/auth
orchestration, resolution, SDK normalization, per-suite metadata/component reads
and JSON output are inside. The SDK stub honors report-suite metadata filters.
Output hashes and SDK enumeration counts matched for every sample. Cold startup
is separate in the raw report and is not used as a speedup claim.

| Workload | Baseline median (range), s | Candidate median (range), s | Runtime reduction |
|---|---|---|---|
| Stats, 200 suites × 100 VRS (20,000 org rows) | 0.974696 (0.954364–1.101324) | 0.579624 (0.542407–0.600880) | 40.53% |
| Stats, 20 suites × 20 VRS (400 org rows) | 0.046408 (0.043915–0.076764) | 0.045990 (0.043331–0.066712) | 0.90%, inconclusive |

| Workload | Python traced peak, baseline → candidate | Process peak RSS, baseline → candidate | Additional retained index |
|---|---|---|---|
| Stress | 7,196,017 → 7,196,017 B | 121,978,880 → 123,699,200 B | 190,920 B |
| Small control | 201,215 → 208,240 B | 100,810,752 → 100,696,064 B | 5,760 B |

Retained-index overhead is a separate shallow-size inspection of `VrsRows`, its
instance dictionary, parent dictionary and bucket lists, excluding original
rows/list and referenced parent strings. Fixtures use the same parent/id shape
and cardinalities; this measures additional retained references, not deep payload
size. RSS includes interpreter/import/fixture high-water marks and is one sample;
it is not an attribution of index memory. The stress runtime exceeds the 10%
gate. Memory is not improved. The small control is noisy and inconclusive; it
was measured once without tuning/repeating fixtures to chase a result. The
stress and control use respectively 201 and 21 report-suite SDK calls (one
organization discovery plus per-suite metadata); both use one VRS enumeration.

Exact benchmark commands (repository root, same interpreter and dependencies):

```bash
mkdir -p /tmp/aa-u3-baseline
git archive b851874fed05708502fcff217760a21363027314 | tar -x -C /tmp/aa-u3-baseline
printf '%s\n' b851874fed05708502fcff217760a21363027314 > /tmp/aa-u3-baseline/.benchmark-source-sha
UV_CACHE_DIR=/tmp/aa-uv-cache uv run --no-sync python benchmarks/performance_arc.py --baseline-root /tmp/aa-u3-baseline --cases stats --rounds 7 --suites 200 --vrs-per-suite 100 --components 1 --output /tmp/aa-u3-stress.json
UV_CACHE_DIR=/tmp/aa-uv-cache uv run --no-sync python benchmarks/performance_arc.py --baseline-root /tmp/aa-u3-baseline --cases stats --rounds 7 --suites 20 --vrs-per-suite 20 --components 1 --output /tmp/aa-u3-small.json
```

Characterization: the pre-change focused source/filter/outcome/CLI-sharing tests
passed (11 tests). The expanded source test module run against the archived
baseline passed 13 behavioral tests and failed the two index-mechanism tests
(no `VrsRows`/indexed `_loaded`), as expected. The candidate focused VRS source,
filter, outcome, resilience, full-expansion and CLI-sharing selection passed all
33 tests. Changed Python files passed Ruff lint/format and `git diff --check`.
The orchestrator runs the authoritative full repository checks.

No count-only model bypass, reduced SDK expansion, network optimization,
persistent cache, cross-invocation reuse or additional retry path was built.
