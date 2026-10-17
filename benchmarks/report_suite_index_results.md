# Invocation-local report-suite resolution index

U2 keeps exact RSID priority, ordered name matches and ambiguity candidates,
Unicode casefolding, and the existing ordered fuzzy fallback. Batch, stats and
inventory construct one index over their successful preloaded discovery listing.
Standalone/list-based resolution remains supported. Raw matching rows are
materialized only when selected, so unrelated missing IDs do not become errors.
Unusual non-string values retain the scan path, including unhashable values.
Failed discovery preloads still fall back to per-identifier SDK resolution.

This is an offline local CPU optimization. Successful discovery, per-suite
metadata reads, request arguments and retry behavior are unchanged. No live
Adobe latency improvement is claimed.

The baseline is archived commit `822f0421b029ea1ec5381c5d79ee875b89912e4f`;
the candidate is that baseline plus this change, identified by source digest in
`report_suite_index_results.json`. Both use one interpreter and lockfile. Each
case has seven alternating paired timing samples and separate allocation runs.
The subprocess warms its operation once. Resolution timing includes identifier
construction, index construction where available, and all resolutions, excluding
fixture construction and imports. Stats/inventory run their complete command
handlers with stub credentials/auth, discovery, resolution, SDK normalization,
per-suite metadata/component reads and JSON output included. Cold `--version`
startup is recorded separately and is not a command speedup measurement.

The reused SDK stub now honors `getReportSuites(rsid_list=...)`: a prebuilt
ID mapping selects metadata rows instead of returning the entire organization
on each metadata read. Unfiltered discovery still returns all rows. This fixes
an artificial quadratic metadata cost in the earlier fixture; both variants
use the corrected stub. Initial incomplete measurements using the old stub were
cancelled and excluded. `sdk_report_suite_enumerations` counts **all**
`getReportSuites` SDK calls (one discovery plus one metadata call per supplied
suite), rather than only organization-wide discovery. No observed HTTP counts
are inferred from these synthetic SDK calls.

Reproduce with the same current harness against an archived baseline:

```bash
mkdir -p /tmp/aa-u2-baseline
git archive 822f0421b029ea1ec5381c5d79ee875b89912e4f | tar -x -C /tmp/aa-u2-baseline
printf '%s\n' 822f0421b029ea1ec5381c5d79ee875b89912e4f > /tmp/aa-u2-baseline/.benchmark-source-sha
uv run --no-sync python benchmarks/performance_arc.py \
  --baseline-root /tmp/aa-u2-baseline --resolution-index \
  --cases resolution-exact resolution-name --rounds 7 --suites 5000 \
  --vrs-per-suite 0 --components 1 --output /tmp/aa-u2-resolution-stress.json
uv run --no-sync python benchmarks/performance_arc.py \
  --baseline-root /tmp/aa-u2-baseline --resolution-index \
  --cases stats inventory --rounds 7 --suites 500 \
  --vrs-per-suite 0 --components 1 --output /tmp/aa-u2-command-stress.json
uv run --no-sync python benchmarks/performance_arc.py \
  --baseline-root /tmp/aa-u2-baseline --resolution-index \
  --cases stats --rounds 7 --suites 1 \
  --vrs-per-suite 0 --components 1 --output /tmp/aa-u2-small.json
```

Resolution stress uses 5,000 suites and 5,000 identifiers, either exact RSIDs or
unique deterministic 20-character names. The command stress uses 500 suites;
the single-suite control uses one. Each command suite has four dimensions,
three metrics, two segments, one calculated metric, one classification dataset,
and zero VRS rows. `--components` affects export fixtures rather than these
command component counts. Organization VRS is deliberately empty to isolate
resolution from parent filtering; successful empty sharing remains exercised.

A repeated single-suite stats comparison is retained because the initial result
was noisy. A 50-suite stats control uses the same command above with
`--suites 50` and `--output /tmp/aa-u2-small-50.json`; it gives a longer small
workload rather than interpreting a few-millisecond ratio as a stable bound.
The raw artifact includes every completed final-source run, including both
single-suite controls.

| Run / workload | Baseline median [min–max] ms | Candidate median [min–max] ms | Median change | Python peak B (base→candidate) | RSS B (base→candidate) |
| --- | ---: | ---: | ---: | ---: | ---: |
| resolution_stress / resolution-exact | 329.469 [317.900–338.729] | 4.198 [4.010–5.382] | -98.73% | 591,814→2,508,814 | 102,957,056→108,249,088 |
| resolution_stress / resolution-name | 2304.000 [2250.748–2351.122] | 5.905 [5.596–33.643] | -99.74% | 712,026→2,628,965 | 101,711,872→106,315,776 |
| command_stress / stats | 1050.948 [1014.443–1074.899] | 1034.828 [965.261–1100.824] | -1.53% | 662,941→838,346 | 101,498,880→101,924,864 |
| command_stress / inventory | 1063.984 [1043.224–1134.530] | 1031.396 [994.161–1147.368] | -3.06% | 693,154→865,799 | 100,745,216→101,515,264 |
| single_suite / stats | 3.197 [2.642–3.929] | 3.405 [2.844–4.291] | +6.51% | 56,862→57,617 | 101,040,128→100,368,384 |
| single_suite_repeat / stats | 3.182 [2.947–4.398] | 3.789 [2.899–4.059] | +19.08% | 56,910→57,716 | 100,466,688→99,713,024 |
| fifty_suite_control / stats | 110.181 [104.469–132.941] | 115.801 [104.653–129.677] | +5.10% | 103,895→123,080 | 100,794,368→99,975,168 |

All semantic hashes and SDK counts matched across all paired samples. Resolution
has zero SDK calls. The 500-suite commands each have 501 getReportSuites calls
and one successful-empty VRS enumeration; 50 suites have 51 and one, and one
suite has two and one. The raw record includes runtime/platform/dependency
versions, source and lock digests, cold startup, and every timing/allocation
sample. RSS is process high-water memory including imports and the warm run;
it is not retained-index size.

The complete local resolution workload earns the runtime target: roughly
98.7% faster for 5,000 exact IDs and 99.7% faster for names, including setup.
The tradeoff is about 1.92 MB extra traced peak for 5,000 indexed rows (about
383 bytes/row in this fixture); this is allocation overhead, not a memory win.
At 500 suites, the command traced peaks increase about 173–175 KB.

Stats/inventory show only 1.5%/3.1% median reductions with overlapping spreads.
These do not demonstrate material whole-command acceleration. Both repeated
single-suite comparisons are noisy, with candidate medians higher by 0.208 ms
and 0.607 ms. The 50-suite control also overlaps and has a +5.1% median.
The proposed 5% small-control non-regression bound remains unresolved; these
samples do not justify a claim that the bound passed. No further timing runs
were used to select a more favorable result.

The end-to-end 10% runtime gate is **NOT met**. Small-control non-regression
is **UNRESOLVED**. Any acceptance exception is provisional pending arc review;
this candidate has not passed all original thresholds.

Retention rationale: this modest invocation-owned index removes demonstrably
quadratic CPU work for large identifier/name lists with a bounded, explicit
memory cost and no persistence or network changes. It is useful for that
nominated workload even though ordinary command acceleration is unproven and
the small-control bound is unresolved. This is the plan's explicit
complexity-versus-benefit exception, subject to review; defer/revert remains
appropriate if that tradeoff is unacceptable.

Considered and not built: persistent/cross-invocation caches, fuzzy-result
caches, metadata reuse, new retry/fallback policies, reduced SDK expansions,
additional user flags, and a general benchmark/profiling platform. Existing
fuzzy scans and standalone list calls retain their behavior.

## Additive single-identifier caller fix control

The simplification pass now builds an invocation index only when the caller has
more than one supplied identifier. A single name may still expand to multiple
suites; that uses the existing list resolver. Failed preloads still fall back
to per-identifier SDK reads. The historical measurements and limitations above
remain unchanged.

This isolated control archives original U2 commit `b851874` under
`/tmp/aa-u2-single-fix`, retaining its original source marker, and applies only
the three batch/stats/inventory caller guards. It includes no later production
units. The corrected current harness compares it with `/tmp/aa-u2-baseline`
(`822f042`) using one suite, 20 VRS rows, seven alternating timing pairs and
separate allocation runs. Raw source/lock identities and all samples are in
`report_suite_index_single_fix.json`.

| Workload | Baseline median [min–max] ms | Candidate median [min–max] ms | Python peak B | RSS B |
| --- | ---: | ---: | ---: | ---: |
| stats, one identifier | 3.512 [3.134–6.256] | 3.420 [2.929–3.594] | 67,050→67,050 | 99,614,720→100,679,680 |

The median is 2.62% lower with identical traced peak allocation. All output
hashes and SDK counts match (two report-suite SDK reads and one VRS read per
operation). The timing ranges overlap, so this tiny control does not establish
a stable 5% non-regression bound; that bound remains **UNRESOLVED**. No tuning
or repeated selection was performed. The whole-command 10% target remains
**NOT met**; retention continues to depend on the explicitly reviewed exception
for large repeated local identifier resolution and its bounded memory cost,
without a universal command-speedup claim.
