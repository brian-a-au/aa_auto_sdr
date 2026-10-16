# JSON file and snapshot payload reuse (U5)

Measured 2026-10-16 on macOS 26.6.2 arm64 with Python 3.14.0. Baseline
`8d5854c768bd0483f4c9898093d06f8946f29c46` was archived to
`/tmp/aa-u5-baseline` with `.benchmark-source-sha`; the candidate is the working
change based on that commit. Production code was finalized before measurement.
No live Adobe calls were made.

The existing `performance_arc.py` harness exercises the real `run_single` file
pipeline with a stub SDK, including fetching, model construction, JSON output,
snapshot envelopes and atomic replacement. Imports, fixture construction,
authentication and one warmup operation are excluded. Each workload uses seven
alternating baseline/candidate wall-time pairs and one separate allocation pair.
Process peak RSS includes interpreter setup and warmup, rather than measuring
only the operation. CPU was reserved for the measured pairs.

| Workload | Baseline wall median (min–max), seconds | Candidate wall median (min–max), seconds | Baseline/candidate Python peak bytes | Baseline/candidate process peak RSS bytes |
| --- | --- | --- | --- | --- |
| 1,000 segments, 100 predicates each | 0.628741 (0.602740–0.659221) | 0.557687 (0.536538–0.662826) | 20,982,481 / 20,972,953 | 167,854,080 / 168,493,056 |
| 10 segments, 3 predicates each | 0.005207 (0.004949–0.005817) | 0.004424 (0.004238–0.007595) | 213,350 / 212,846 | 100,941,824 / 101,433,344 |

The stress case passes the 10% runtime gate with an 11.30% reduction in median
complete-workload time; six of seven paired observations improve. Peak Python
allocation is effectively unchanged (0.05% lower). Retaining the JSON payload
through snapshot save removes a second conversion but keeps that payload alive
between writers. Process peak RSS was 0.38% higher in the stress allocation run
and 0.49% higher in the small run; these single process-wide measurements do not
establish a repeatable memory increase or a memory improvement.

The small median is 15.05% lower, with broad spread: four pairs improve and three
slow down (two by less than 5%, one outlier by 45.64%). This does not show a
repeatable greater-than-5% small-control regression or support a precise small
speedup claim. No fixture sweep or tuning reruns were performed.

All samples match parsed JSON file and snapshot semantic hashes and SDK counts:
one report-suite enumeration and one VRS enumeration per operation, unchanged.
These are SDK enumerations, not observed HTTP request counts. Stress output hash:
`b099d3a90bd7e9a5a57f2ebc66e3d6c3553eab47900eb839b57f14e79b3fea62`.
Small output hash:
`2f11b5300bfe6f3abf270f52527cec5e9e0048b7ffdcedac3d22773a09e2dfe8`.
Focused tests additionally compare output bytes, quality/degraded/partial
metadata, conversion counts, input/payload nonmutation, parallel isolation,
custom writer/subclass behavior and actual atomic-write failures.

Source-tree hashes: baseline
`8cc3ed374580da7b47ce395e6eaa6de935944ae459cd7d8237d25ac5f48566a0`;
candidate `01ed1fd735831abb4b680e9b3a2e5a51c179a34261609cb6016a96a16aa9e930`.
Both lock hashes:
`3e0275f6d274eaf453c93d58e66de718d1263afa9b4c3fbed91a0b7181c568b7`.
Both sources use the same interpreter and aanalytics2 0.5.5.post2, pandas 3.0.6,
numpy 2.4.4, openpyxl 3.1.5 and XlsxWriter 3.2.9.

Raw samples, source identities, fixtures and single-observation cold CLI startup
measurements are in [json_snapshot_payload_stress.json](json_snapshot_payload_stress.json)
and [json_snapshot_payload_small.json](json_snapshot_payload_small.json). Cold
startup observations are outside the warm workload claim.

Reproduce from the repository root:

```sh
UV_CACHE_DIR=/tmp/aa-uv-cache uv run --no-sync python benchmarks/performance_arc.py --baseline-root /tmp/aa-u5-baseline --cases json-snapshot --components 1000 --depth 100 --rounds 7 --output benchmarks/json_snapshot_payload_stress.json
UV_CACHE_DIR=/tmp/aa-uv-cache uv run --no-sync python benchmarks/performance_arc.py --baseline-root /tmp/aa-u5-baseline --cases json-snapshot --components 10 --depth 3 --rounds 7 --output benchmarks/json_snapshot_payload_small.json
```

No global serialization cache, writer protocol extension, new flag, network
change, stdout optimization, template change or Notion change was needed.
Custom JSON registrations and subclasses retain their public `write()` path;
only the exact built-in writer opts into the internal payload route.
