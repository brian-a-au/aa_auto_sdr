# aa_auto_sdr — benchmark results

This file accumulates benchmark results from `benchmarks/*.py` scripts.
Run a benchmark with `uv run python benchmarks/<script>.py`; the script
appends a results section here.

Mock-based benchmarks measure SDK call shape only — they don't reflect
real network or AA-server latency. Use them to track relative changes
between versions, not absolute performance.

## v1.7.2 — 2026-05-09 20:21

Mock-based benchmark of fetch_virtual_report_suites with `count_only=True`
vs default ladder (`extended_info=True`).

| rows | full_ms | minimal_ms | speedup |
|---:|---:|---:|---:|
| 10 | 7.16 | 1.54 | 4.66x |
| 50 | 29.41 | 6.60 | 4.45x |
| 200 | 106.58 | 24.49 | 4.35x |

## v1.8.0 — 2026-05-09 — `--workers N` live-org wall-clock

Live run against the `lumaac0` Adobe Analytics company on demo data.
Four RSIDs, each generating one JSON SDR file:

- `dgeo1xxpnwcidadobestore` (Adobe Store)
- `dgeo1xxpnwcidcjab2b` (Demo Data CJA)
- `dgeo1xxpnwcidluma` (Demo Data)
- `egeo1xxpnwcidevangelists` (Demo Data Evangelists)

| --workers | wall-clock (s) | speedup vs. seq | per-RSID avg (s) |
|---:|---:|---:|---:|
| 1 (sequential) | 18.1 | 1.00× (baseline) | 4.52 |
| 2 | 9.0 | 2.01× | 2.25 |
| 4 | 11.8 | 1.53× | 2.94 |

Notes:

- `--workers 2` hits a 2.01× speedup — within the spec §11.1 target of
  2–3× for parallel runs. Sweet spot for this org.
- `--workers 4` underperforms `--workers 2` (1.53× vs. 2.01×). Consistent
  with API rate limiting on Adobe demo orgs: more concurrent requests →
  throttling overhead dominates the gains. Per-RSID wall-clock under
  workers=4 (~11.7s for the three slow ones) is roughly equal to total
  batch wall-clock, suggesting all four submitted simultaneously then
  serialized at the AA endpoint.
- Sequential per-RSID durations (3.7, 2.4, 5.1, 6.9s) sum to 18.1s —
  matches the workers=1 wall-clock exactly. Validates that
  `RunResult.duration_seconds` is now stamped correctly on the parallel
  path (regression fix from PR #30 ultrareview, bug_001).
- Real-world recommendation: start with `--workers 2`, scale up only
  after verifying the target org doesn't throttle. `--workers 16` (the
  cap) is unlikely to help any single AA org and may degrade throughput.
