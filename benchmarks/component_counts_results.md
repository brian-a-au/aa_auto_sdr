# Component counts (U6): deferred

U6 is deferred. The final candidate reduced median complete rich-stats elapsed
by 23.41% and peak Python allocation by 64.28%, but small stats slowed by 10.02%
in the final seven-pair run after a 5.60% slowdown in the initial run. Those gains
are insufficient to satisfy the plan's requirement of no repeatable slowdown
greater than 5% on small controls. Production code and tests were restored to
baseline; no U6 optimization ships and no changelog claim was added.

Measured 2026-10-16 using CPython 3.14.0 on macOS arm64. Baseline
`0267030c228bd24b21c00c1910ef3929a1a3f0f6` was archived under
`/tmp/u6-baseline-0267030`. Each comparison used the same interpreter and locked
dependencies, seven alternating baseline/candidate wall-time pairs, and a
separate allocation pair. Imports, fixture construction, authentication, and one
warmup operation are excluded. Complete stats credential/resolve orchestration,
SDK stub enumeration, normalization, aggregation, and JSON rendering are included.
There is no network latency simulation or live Adobe access. SDK enumeration
counts are not observed HTTP requests. Process peak RSS includes imports and
warmup and is not scoped to the measured operation; Python peak uses tracemalloc.

The bounded [helper](component_counts.py) honors string and list `rsid_list`,
returns raw lists for `format="raw"` segment/calculated-metric calls, and otherwise
returns DataFrames. This correction applies equally to both compared source
trees. It does not alter earlier arc benchmark fixtures or claim their shape
correction as an optimization.

The rich workload uses 20 suites, each with 200 dimensions, 200 metrics, 1,000
segments, 200 calculated metrics, the existing sample classifications, and ten
VRS. Rows repeat the actual test fixture's shape with unique IDs. Small stats
uses one suite, unchanged sample components, and ten VRS. The full-fetch control
fetches and retains all four ordinary component lists for one rich suite; result
hashing occurs after timing. It is a focused normalization control, not an SDR
writer benchmark. Inventory and describe were checked for output/status parity,
not independently timed.

| Final workload | Baseline median (min–max), seconds | Candidate median (min–max), seconds | Time change | Baseline/candidate Python peak bytes | Baseline/candidate process peak RSS bytes |
| --- | --- | --- | --- | --- | --- |
| stress | 0.123660 (0.118171–0.249578) | 0.094716 (0.092392–0.096820) | -23.41% | 544,350 / 194,432 | 100,139,008 / 99,778,560 |
| small | 0.001854 (0.001791–0.002095) | 0.002040 (0.001824–0.002415) | +10.02% | 58,382 / 58,431 | 98,385,920 / 98,369,536 |
| full_control | 0.005515 (0.005373–0.006230) | 0.005424 (0.005085–0.013530) | -1.64% | 586,976 / 587,033 | 100,974,592 / 100,745,216 |
Rich stats improved in seven of seven pairs; small stats slowed in five of seven
pairs (four by more than 5%). The final full-fetch control improved in four of
seven pairs and has an outlier; it does not establish a precise speedup. Small
stats' absolute median increase is approximately 0.186ms, but its relative
regression repeated, so the candidate was not retained. No further tuning or
measurement sweep followed.

The initially measured implementation selected the same model constructor or a
sink and evaluated exactly the existing keyword conversion expressions in a
generator. It preserved `_records`, SDK arguments, retry wrappers, error
boundaries, conversion order, and logging, and left VRS/classification fetching
unchanged. Counts streamed without retaining models. Its rich stats improved
21.76% with 64.30% lower Python peak, but small stats slowed 5.60% and full fetching
slowed 7.14%. One bounded simplification restored the original list-comprehension
shape: full mode constructed models, count mode retained only `None` placeholders
and returned the list length. The final table measures that version. This resolved
the full-fetch regression but did not resolve the small-control regression.

All final samples match output hashes and SDK enumeration counts. Rich stats
uses one VRS enumeration, 21 suite enumerations, and 20 enumerations of each
ordinary/classification component. Small stats uses one VRS enumeration, two
suite enumerations, and one enumeration of each other component. Full control
uses one enumeration of each of its four components. Semantic hashes:

- Rich stats: `14895a14dd24e68e14c10d16444a421ca6936a49c35b9ede139070ac45697cd5`.
- Small stats: `1e124539cf395a349fe841fe011916771f47af6d8776c42754a8654f10dacde7`.
- Full control: `5a55492a4cc68bee87d3e5b556b7045146a16bd20c48e04b8a0244d77042e63b`.

226 focused API/CLI cases passed before final measurements, covering full-fetch
values, healthy/empty/ragged/malformed count equivalence, retry/request arguments,
model-allocation avoidance, and stats/inventory/describe JSON/CSV/table output
with healthy/partial/degraded fetch metadata. Changed-path Ruff checks passed.
Candidate-only tests were removed with the rejected implementation. The host
orchestrator owns authoritative final repository verification.

Final raw records:
[rich stats](component_counts_stress.json), [small stats](component_counts_small.json),
[full control](component_counts_full_control.json). Baseline source hash:
`01ed1fd735831abb4b680e9b3a2e5a51c179a34261609cb6016a96a16aa9e930`;
final rejected candidate source hash:
`1f9a3dbbfeb9f52cbb4810b99d0c743dafdc9516d317035d641adbbb9dbd793c`.
Both lock hashes:
`3e0275f6d274eaf453c93d58e66de718d1263afa9b4c3fbed91a0b7181c568b7`.
The rejected production/test patch, new tests, fetch.py, and identity record are
archived locally at `/tmp/u6-rejected-candidate`; initial generator observations
are at `/tmp/u6-generator-iteration`. Those local archives are not distributed
with the repository. Applying the archived patch and new tests to the baseline
reconstructs the final rejected candidate for local investigation.

To reproduce the fixed workload comparison against an explicitly reconstructed
candidate (running against the restored production tree will compare baseline
behavior):

```sh
UV_CACHE_DIR=/tmp/uv-u6-cache uv run --no-sync python benchmarks/component_counts.py \
  --baseline-root /tmp/u6-baseline-0267030 --candidate-root /path/to/reconstructed-candidate \
  --case stats-rich --output /tmp/component-counts-stress.json
```

Repeat with `--case stats-small` and `--case full-rich`. No live timing or RSS
improvement is claimed. A future candidate must address the small-control cost
and satisfy the complete gate; plain `len(raws)` or reduced SDK expansion remains
outside the preserved-semantics approach.
