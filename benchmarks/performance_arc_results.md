# Performance arc baseline controls

These are offline measurement controls, not optimization or live API speedup
claims. Both variants use the same archived production source and dependencies.
Seven paired wall samples alternate baseline/candidate order. Each subprocess
warms its operation once; the measured invocation excludes imports, fixture
construction and authentication. Allocation tracing runs separately from wall
samples. The raw samples, source SHA, source digest, lock digest, runtime,
platform and dependency versions are in `performance_arc_results.json`.

Reproduce the archived source (no checkout/index change):

```bash
mkdir -p /tmp/aa-u1-baseline
git archive ea74d3f | tar -x -C /tmp/aa-u1-baseline
git rev-parse ea74d3f > /tmp/aa-u1-baseline/.benchmark-source-sha
UV_CACHE_DIR=/tmp/aa-u1-uv-cache uv run --no-sync python benchmarks/performance_arc.py \
  --baseline-root /tmp/aa-u1-baseline --candidate-root /tmp/aa-u1-baseline \
  --suites 1 --components 3 --depth 3 --snapshots 3 --rounds 7 \
  --output /tmp/aa-u1-identical.json
```

The initial wall samples were retained. Allocation samples were refreshed after
moving RSS capture ahead of workbook/JSON semantic verification; dependency
metadata and listing counters were refreshed too. Excel was then rerun for seven pairs with the expanded workbook semantic hash.
Production source trees were unchanged. A fresh run of the command above uses the corrected sampler directly.

The small control uses one suite, 20 organization VRS rows, three export/trending segments with
three nested predicates, and three snapshots. `--suites 50` and `--suites 500`
select organization/stress fixtures; `--vrs-per-suite`, `--components`, `--depth`
and `--snapshots` vary independent dimensions. `--cases` limits cost. Defaults
use 50 suites and 1,000 segments with 20 predicates. Do not treat this small
control as evidence about a large export or organization.

Workload boundaries:

- Batch runs include real batch orchestration, real builds and JSON files;
  stats/inventory run their command handlers with stub credentials and SDK.
  Both receive supplied exact IDs. SDK latency is zero. Counts are SDK method
  enumerations, not HTTP requests or SDK pagination.
- Resolution runs resolve every supplied ID/name against a preloaded listing;
  listing discovery and authentication are excluded. Fuzzy fixtures append a
  character to distinct hashed names. Future index construction belongs inside
  this timed operation. Use stats/inventory for whole-command corroboration.
- Excel and JSON+snapshot run the actual single-suite pipeline and real build
  against a stub SDK, with repeated nested segment definitions. They include
  conversion, serialization and filesystem writes. JSON+snapshot exercises
  the pipeline's payload-sharing boundary.
- Trending reads actual saved snapshots and runs the existing comparator;
  history preparation is excluded. This is an unchanged local control.
- Cold CLI `--version` startup is one separate, untraced observation per source;
  it is not a full authenticated generation command or a seven-pair comparison.

Semantic hashes compare parsed JSON/snapshot payloads, resolution results,
trending dataclasses, and workbook sheet order, cell values/types/number formats/style IDs, hyperlink
targets, column widths, row heights, filters and freeze panes. Workbook ZIP timestamps are excluded. This is a benchmark equivalence
check; existing writer tests remain the broader presentation contract.

Peak Python bytes come from one separate traced invocation per variant.
RSS is process high-water memory including imports and warmup, captured before
semantic verification; it is unavailable where `resource` is unsupported.
It is not an isolated incremental operation allocation measurement.

## Identical-source observations

| Case | Baseline median ms (min–max) | Identical candidate ms (min–max) | Python peak KiB B/C | RSS MiB B/C | VRS/listing enumerations |
| --- | --- | --- | --- | --- | --- |
| batch-sequential | 5.818 (4.283–11.399) | 7.771 (4.495–12.398) | 205.1/205.1 | 95.6/96.3 | 1/1 |
| batch-parallel | 4.593 (4.093–5.115) | 4.438 (4.146–5.128) | 219.9/219.9 | 96.6/96.5 | 1/1 |
| stats | 3.729 (3.051–5.721) | 4.151 (3.636–6.042) | 65.4/65.3 | 96.0/96.2 | 1/2 |
| inventory | 3.698 (3.043–4.302) | 3.917 (3.245–7.424) | 65.5/65.5 | 96.0/95.0 | 1/2 |
| resolution-exact | 0.003 (0.003–0.004) | 0.003 (0.003–0.013) | 8.7/8.7 | 95.2/94.3 | 0/0 |
| resolution-name | 0.004 (0.004–0.005) | 0.004 (0.004–0.005) | 8.7/8.7 | 95.1/94.5 | 0/0 |
| resolution-fuzzy | 0.022 (0.022–0.024) | 0.024 (0.022–0.024) | 8.8/8.8 | 95.4/94.8 | 0/0 |
| excel | 39.425 (26.574–47.807) | 38.359 (25.973–42.613) | 776.6/776.9 | 100.7/100.5 | 1/1 |
| json-snapshot | 6.825 (4.171–13.133) | 8.090 (5.105–16.485) | 178.2/178.2 | 95.2/96.0 | 1/1 |
| trending | 0.383 (0.373–0.491) | 0.407 (0.361–0.634) | 147.9/147.9 | 95.1/94.7 | 0/0 |

All paired semantic hashes matched; SDK enumeration counts matched. Very short
operations show substantial relative noise, and these small samples establish
no improvement or regression. Use absolute medians/spread and repeat declared
stress workloads before deciding an optimization gate. An earlier Excel control
had medians of 29/56 ms; its expanded-semantic rerun above had 39/38 ms, another
reason not to infer a speedup from tiny-fixture ratios.

Cold CLI version startup (one observation, not a comparison gate): baseline 0.051s, candidate 0.034s.

Size-capability smokes (single untraced runs, not paired evidence):

- Preloaded name resolution, 50 suites/identifiers: 0.256 ms; no SDK enumerations; successful semantic result.
- Preloaded name resolution, 500 suites/identifiers: 23.991 ms; no SDK enumerations; successful semantic result.

These smoke runs use `--source-root /tmp/aa-u1-baseline --workload resolution-name
--suites 50` (and `500`) with `--components 3`.

Considered and not built: a general profiling framework, synthetic HTTP page
estimates, timing thresholds in pytest, production caches, new concurrency,
SDK query changes, and optimization code. RSS availability handling is limited
to the standard-library platform capability. No live credentials were used.
