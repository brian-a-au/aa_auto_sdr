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
