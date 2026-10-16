# Final combined performance arc check

This required interaction check compares archived baseline `ea74d3f` with final
working source based on `0267030` plus the reviewed simplifications. It is not
a new optimization gate. U6 counts-first production work is excluded; its
separate benchmark evidence remains available. No source or harness changes
were made after measurement began.

The offline fixtures use one interpreter/dependency set, seven alternating
paired timing samples per case, and one separate allocation run per variant.
Stats uses 200 suites with 100 VRS rows each. Excel and JSON+snapshot each use
1,000 nested segment components with 100 predicates per definition. Exports
exercise the real single pipeline with a stub SDK. Auth, imports and fixture
construction are excluded from warm timing. No live API or HTTP latency claims.

| Case | Baseline median [min–max] ms | Candidate median [min–max] ms | Median change | Python peak B (base→candidate) | RSS B (base→candidate) |
| --- | ---: | ---: | ---: | ---: | ---: |
| stats | 966.532 [933.158–1013.725] | 578.160 [549.935–600.342] | -40.18% | 7,129,233→7,196,017 | 121,667,584→123,305,984 |
| excel | 214.874 [202.511–274.714] | 161.559 [135.678–213.800] | -24.81% | 24,546,950→5,424,861 | 182,648,832→148,979,712 |
| json-snapshot | 630.945 [601.916–655.431] | 569.869 [534.781–653.512] | -9.68% | 20,982,431→20,973,002 | 170,262,528→169,115,648 |

All output semantic hashes and SDK enumeration counts match across every
paired sample and allocation run. Stats has 201 report-suite SDK reads and
one VRS read; each export has one of each. These synthetic counts do not
represent observed HTTP request counts. Excel comparison includes workbook
structure, cell values/types/formats/styles, hyperlinks, dimensions, filters
and freeze panes; ZIP timestamps are excluded. JSON/snapshot payloads and
input-document preservation are checked by the harness.

The final combination reduces median time in these nominated cases. Stats
has a small traced-allocation increase; Excel has a substantial traced-peak
reduction. JSON+snapshot has nearly unchanged traced peak and overlapping
wall-time ranges, so the 9.68% median reduction is descriptive evidence only.
RSS is process high-water memory including imports and warmup, not incremental
retained allocation. Prior unit-level evidence and its limitations remain valid;
this combined check does not establish universal gains or resolve U2’s tiny
control uncertainty or whole-command 10% target.

Source identities (full raw samples, runtime and dependency versions are in
`performance_arc_final.json`):

- baseline: git marker `ea74d3fa523553111e7febfc8be60542af3db048`, source SHA-256 `23d02670f3ebec2a5dbc7ee906e79f7bdd6f3aa5f9835c9f7ea898a2c209c428`.
- candidate: git marker `0267030c228bd24b21c00c1910ef3929a1a3f0f6`, source SHA-256 `da9fd4ea6abedd56da4ca71231217ba6a7bc59bc8d3075c6be56456c433f1511`.
- Shared lock SHA-256: `3e0275f6d274eaf453c93d58e66de718d1263afa9b4c3fbed91a0b7181c568b7`.
- Harness SHA-256: `0b24fc9f5e734f6b78682c63d9f901652bb0344e742c3e5201727c4982153319`.

Reproduce:

```bash
UV_CACHE_DIR=/tmp/aa-uv-cache uv run --no-sync python benchmarks/performance_arc.py \
  --baseline-root /tmp/aa-u1-baseline --cases stats excel json-snapshot \
  --rounds 7 --suites 200 --vrs-per-suite 100 --components 1000 --depth 100 \
  --output benchmarks/performance_arc_final.json
```
