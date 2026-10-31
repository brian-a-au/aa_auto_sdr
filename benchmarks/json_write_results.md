# JSON write: one `json.dumps()` call instead of streaming `json.dump()`

`core/json_io.write_json` backs the JSON SDR writer and every snapshot save.
It used `json.dump(payload, fh, indent=2, ...)`, which always runs the
pure-Python encoder and calls `write()` once per token. It now writes one
`json.dumps(...)` string. On Python 3.13 and later the one-shot call uses the
C encoder even with `indent`, so the gain is large there and modest on 3.11
and 3.12. The bytes written are identical on every version.

Machine: Apple Silicon macOS. Each number is the median of 7 samples, with
the two variants run in alternating order.

## Write step only (`benchmarks/json_write.py`, 7,660 components)

| Python | `json.dump` (before) | `json.dumps` (after) | Change |
| --- | ---: | ---: | ---: |
| 3.11.17 | 116.4 ms | 103.4 ms | −11.2% |
| 3.12.13 | 110.0 ms | 96.3 ms | −12.5% |
| 3.13.11 | 99.5 ms | 21.0 ms | −78.9% |
| 3.14.0 | 93.0 ms | 21.3 ms | −77.1% |
| 3.15.0 | 110.7 ms | 19.0 ms | −82.8% |

Every run produced the same SHA-256 (`8ddbb08340f85988…`) for both variants.

## Whole `run_single` pipeline, Python 3.14

A stub SDK serves 3,000 dimensions, 1,500 metrics, 2,000 segments, 800
calculated metrics, 60 virtual report suites and 300 classification
datasets. No network.

| Run | Before | After | Change |
| --- | ---: | ---: | ---: |
| `--format json` | 245.1 ms | 156.5 ms | −36% |
| `--format json` + snapshot save | 338.8 ms | 181.9 ms | −46% |

Reproduce the write-step table:

```bash
uv run python benchmarks/json_write.py
PYTHONPATH=src python3.11 benchmarks/json_write.py
```
