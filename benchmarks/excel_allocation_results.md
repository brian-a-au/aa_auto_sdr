# Excel allocation comparison (U4)

Measured 2026-10-16 on macOS 26.6.2 arm64, Python 3.14.0. This compares
baseline `a290aeee58f0084692edc752acb0826a49be9e99`, archived under
`/tmp/aa-u4-baseline-a290aee` with `.benchmark-source-sha`, against the working
candidate based on that commit. Candidate production code was finalized before
measurement. No live API calls were made.

The existing `performance_arc.py` harness runs the real `run_single` pipeline
against a stub SDK: fetching, model construction, workbook formatting and atomic
replacement are included. Imports, fixture setup, authentication, and one warmup
operation are excluded. Each case uses seven alternating baseline/candidate
subprocess pairs; a separate traced pair measures Python allocation. Process
peak RSS includes interpreter setup and warmup and is not an incremental
operation-only memory measurement. CPU was reserved for these comparisons.

| Workload | Baseline wall median (min–max), seconds | Candidate wall median (min–max), seconds | Baseline/candidate Python peak bytes | Baseline/candidate process peak RSS bytes |
| --- | --- | --- | --- | --- |
| 1,000 segments, 100 predicates each | 0.31135 (0.22425–0.52330) | 0.22229 (0.14531–0.25976) | 24,547,049 / 5,424,793 | 182,124,544 / 149,372,928 |
| 10 segments, 3 predicates each | 0.05506 (0.03454–0.07984) | 0.03257 (0.02554–0.05650) | 812,294 / 732,432 | 105,447,424 / 104,448,000 |

The nominated stress case passes the gate: median runtime falls 28.6% and
traced peak allocation falls 77.9%, exceeding the 10% runtime or 20% memory
threshold. Every stress pair improved elapsed time. The small control median
falls 40.8%; one pair slowed down amid broad timing spread, so these measurements
do not support a precise small-workload speedup or a repeatable >5% regression.
No fixture sweep or tuning reruns were performed. XlsxWriter still retains
workbook state; this change does not provide bounded workbook memory.

All runs matched workbook semantic hashes and SDK enumeration counts (one VRS
and one report-suite enumeration per operation, unchanged). These SDK counts
are not observed HTTP request counts. Hash comparison covers values/types,
hyperlinks, styles, widths, row heights, filters, freezes and sheet order; input
nonmutation is also checked. Stress output hash:
`1f51050acaf7511ff22f726195175c429ab8eef62a0266a21c9f11232731a394`.
Small output hash:
`04c1443473f53a0f66e3512e8b9da4a4c4499dafcb28bebe4a1d7d72bec6cfdc`.

Source-tree hashes: baseline
`8814a32fd6a73f6b035736dd75c729485be330120c4823b6829c9c13dbbb54a7`;
candidate `8cc3ed374580da7b47ce395e6eaa6de935944ae459cd7d8237d25ac5f48566a0`.
Both lockfile hashes:
`3e0275f6d274eaf453c93d58e66de718d1263afa9b4c3fbed91a0b7181c568b7`.
Both use aanalytics2 0.5.5.post2, pandas 3.0.6, numpy 2.4.4, openpyxl 3.1.5,
and XlsxWriter 3.2.9 in the same interpreter environment.

Raw samples, identities, fixtures and cold CLI startup observations are retained
in [excel_allocation_stress.json](excel_allocation_stress.json) and
[excel_allocation_small.json](excel_allocation_small.json). Cold startup is a
single observation per source, outside the warm workload claim.

Reproduce from the repository root (using the archived baseline above):

```sh
UV_CACHE_DIR=/tmp/aa-u4-uv uv run --no-sync python benchmarks/performance_arc.py --baseline-root /tmp/aa-u4-baseline-a290aee --cases excel --rounds 7 --components 1000 --depth 100 --output benchmarks/excel_allocation_stress.json
UV_CACHE_DIR=/tmp/aa-u4-uv uv run --no-sync python benchmarks/performance_arc.py --baseline-root /tmp/aa-u4-baseline-a290aee --cases excel --rounds 7 --components 10 --depth 3 --output benchmarks/excel_allocation_small.json
```
