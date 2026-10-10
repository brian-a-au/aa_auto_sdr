# Invocation-scoped VRS sharing measurements

Measured on 2026-10-09 against baseline `0dbdb604530adcfba7bf9d7aeb563b75f640d0f6` (PR #134). Both source trees used the same locked dependencies: Python 3.14.0, aanalytics2 0.5.5.post2, pandas 3.0.6, NumPy 2.4.4.

## Workload and method

Each complete workload consumed 50 suites with 20 VRS rows per suite (1,000 organization rows). Every fake SDK call incurred 5 ms latency. Batch generation wrote full JSON SDRs; stats and inventory rendered JSON counts. Parallel batch used eight workers.

Each sample ran in a fresh subprocess with one unmeasured warm invocation, followed by a fresh measured invocation. Five recorded baseline/candidate rounds alternated execution order. A separate semantic comparison preceded measurement; every recorded sample also matched the baseline output hash. No test or build jobs ran concurrently.

## Results

| Workload | Baseline seconds, median [min–max] | Candidate seconds, median [min–max] | Runtime reduction | Peak Python bytes, baseline → candidate |
|---|---:|---:|---:|---:|
| batch-sequential | 3.570 [3.526–3.996] | 2.617 [2.598–2.674] | 26.7% | 496,411 → 629,480 |
| batch-parallel | 1.236 [1.182–1.282] | 0.575 [0.568–0.623] | 53.5% | 1,772,979 → 1,421,659 |
| stats | 3.330 [3.305–3.406] | 2.401 [2.327–2.410] | 27.9% | 450,542 → 404,753 |
| inventory | 3.318 [3.291–3.332] | 2.368 [2.344–2.385] | 28.6% | 450,149 → 404,753 |

Every workload reduced successful organization SDK enumerations from **50 to 1**. The fake pagination counter likewise changed from 50 to 1 at 1,000 rows per page. These are simulated page counts, not observed HTTP requests; real SDK calls may span multiple pages.

Sequential peak allocation increased by 133,069 bytes (130 KiB; 26.8%) because the organization rows remain available across suites. Parallel peak allocation fell 19.8%; stats and inventory fell about 10%. The retained data lives only for the invocation. For this workload, the small absolute sequential increase is acceptable alongside lower runtime and enumeration count. This does not establish a memory bound for much larger organizations.

## Reproduce

Extract the baseline commit into a separate directory, retain this harness in the candidate tree, and use one environment synchronized to the candidate lockfile:

```bash
uv run --no-sync python benchmarks/vrs_invocation_sharing.py \
  --baseline-root /tmp/aa-pr-c-baseline-0dbdb60 --candidate-root . \
  --rounds 5 --suites 50 --vrs-per-suite 20 --latency-ms 5 --workers 8 \
  --output /tmp/aa-pr-c-benchmark.json
```

See [recorded samples and source identities](vrs_invocation_sharing_results.json) for timings, output hashes, source digests, and the shared lock digest. Allocation is measured with `tracemalloc` and excludes native allocations/RSS. Fixture setup and imports are outside measurement. Fixed fake SDK latency does not model network variability, throttling, or real SDK pagination cost. No live API speedup is claimed.
