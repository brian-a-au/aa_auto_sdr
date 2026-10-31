"""Compare streaming json.dump() against one json.dumps() write in write_json.

Run: uv run python benchmarks/json_write.py [--components 7660] [--repeats 7]
Stdlib only, so any interpreter works: PYTHONPATH=src python3.11 benchmarks/json_write.py
Synthetic snapshot-shaped payload; timings cover serialization and the file
write only. Both variants must produce identical bytes or the run fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import tempfile
import time
from pathlib import Path

from aa_auto_sdr.core.json_io import write_json


def streaming_write_json(path: Path, payload: object, *, indent: int = 2) -> None:
    """write_json as it was before the change: json.dump() onto the handle."""
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=indent, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp_str, path)


def payload(components: int) -> dict:
    def row(i: int) -> dict:
        return {
            "id": f"variables/evar{i}",
            "name": f"Component {i} ünïcode 日本",
            "description": "Authenticated user identifier",
            "tags": [],
            "extra": {"category": "Conversion", "pathable": False, "precision": i % 4},
            "definition": {"func": "segment", "container": {"pred": {"func": "streq", "str": str(i)}}},
        }

    return {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "bench",
        "components": {"dimensions": [row(i) for i in range(components)]},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--components", type=int, default=7660)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    data = payload(args.components)
    variants = {"json.dump (before)": streaming_write_json, "json.dumps (after)": write_json}
    samples: dict[str, list[float]] = {name: [] for name in variants}
    digests: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as folder:
        for fn in variants.values():  # warm-up
            fn(Path(folder) / "warm.json", data)
        for i in range(args.repeats):
            # Alternate order to reduce filesystem-cache / thermal bias.
            order = list(variants) if i % 2 == 0 else list(reversed(variants))
            for name in order:
                target = Path(folder) / f"{i}-{list(variants).index(name)}.json"
                started = time.perf_counter()
                variants[name](target, data)
                samples[name].append((time.perf_counter() - started) * 1000)
                digests.setdefault(name, hashlib.sha256(target.read_bytes()).hexdigest())
    if len(set(digests.values())) != 1:
        raise SystemExit(f"output bytes differ: {digests}")
    before, after = (statistics.median(samples[name]) for name in variants)
    print(f"Python {platform.python_version()}, {args.components} components, {args.repeats} samples")
    for name in variants:
        print(f"  {name:20s} median {statistics.median(samples[name]):8.1f} ms  min {min(samples[name]):8.1f} ms")
    print(f"  change {(after / before - 1) * 100:+.1f}%  identical bytes: sha256 {next(iter(digests.values()))[:16]}")


if __name__ == "__main__":
    main()
