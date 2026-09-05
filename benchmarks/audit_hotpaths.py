"""Compare local hot paths against a git revision, without network access.

Run: uv run python benchmarks/audit_hotpaths.py --baseline-ref 7fe9676
Synthetic workloads; timings exclude imports and fixture construction.
"""

from __future__ import annotations

import argparse
import importlib
import json
import statistics
import subprocess
import time
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

from aa_auto_sdr.api.models import ReportSuite, Segment
from aa_auto_sdr.sdr.document import SdrDocument

ROOT = Path(__file__).resolve().parents[1]


def baseline_module(ref: str, name: str) -> ModuleType:
    path = "src/" + name.replace(".", "/") + ".py"
    source = subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True)
    module = ModuleType("baseline_" + name)
    exec(compile(source, path, "exec"), module.__dict__)  # noqa: S102 — explicitly selected local git source
    return module


def measure(before, after, *, repeats: int) -> dict[str, float]:
    samples: list[list[float]] = [[], []]
    for i in range(repeats):
        # Alternate order to reduce filesystem-cache / thermal bias.
        for idx in (0, 1) if i % 2 == 0 else (1, 0):
            start = time.perf_counter()
            (before, after)[idx]()
            samples[idx].append(time.perf_counter() - start)
    old, new = (statistics.median(s) * 1000 for s in samples)
    return {"before_ms": round(old, 3), "after_ms": round(new, 3), "speedup": round(old / new, 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default="7fe9676")
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    results = {}
    name = "aa_auto_sdr.pipeline.sampling"
    old, new = baseline_module(args.baseline_ref, name), importlib.import_module(name)
    for size in (3000, 30000):
        rsids = [f"{prefix}_{i}" for prefix in ("prod", "stage", "dev") for i in range(size // 3)]
        kwargs = {"sample_size": size // 2 + 1, "seed": 42, "stratified": True}
        assert old.sample_rsids(rsids, **kwargs) == new.sample_rsids(rsids, **kwargs)
        results[f"sampling_{size}"] = measure(
            partial(old.sample_rsids, rsids, **kwargs),
            partial(new.sample_rsids, rsids, **kwargs),
            repeats=args.repeats,
        )

    doc = SdrDocument(
        report_suite=ReportSuite("synthetic.prod", "Synthetic", "UTC", "USD", None),
        dimensions=[],
        metrics=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        segments=[
            Segment(
                id=f"s{i}",
                name=f"Segment {i} | <example>",
                description="Line one\nLine two",
                rsid="synthetic.prod",
                owner_id=1,
                definition={
                    "container": {
                        "func": "and",
                        "preds": [
                            {"func": "eq", "val": {"name": "variables/evar1"}, "str": f"value{j}"} for j in range(20)
                        ],
                    }
                },
                compatibility={},
                tags=["example", "benchmark"],
                created=None,
                modified=None,
                extra={"nested": {"values": [1, None, True]}},
            )
            for i in range(1000)
        ],
        captured_at=datetime(2026, 9, 4, tzinfo=UTC),
        tool_version="benchmark",
    )
    original = doc.to_dict()
    with TemporaryDirectory(prefix="aa-audit-benchmark-") as temp:
        for fmt, cls in (("csv", "CsvWriter"), ("markdown", "MarkdownWriter"), ("html", "HtmlWriter")):
            name = f"aa_auto_sdr.output.writers.{fmt}"
            old_writer = getattr(baseline_module(args.baseline_ref, name), cls)()
            new_writer = getattr(importlib.import_module(name), cls)()
            old_path = Path(temp) / "before" / ("report" + old_writer.extension)
            new_path = Path(temp) / "after" / ("report" + new_writer.extension)
            old_files = old_writer.write(doc, old_path)
            new_files = new_writer.write(doc, new_path)
            assert [p.name for p in old_files] == [p.name for p in new_files]
            assert [p.read_bytes() for p in old_files] == [p.read_bytes() for p in new_files]
            results[f"{fmt}_1000_segments"] = measure(
                partial(old_writer.write, doc, old_path),
                partial(new_writer.write, doc, new_path),
                repeats=args.repeats,
            )
    assert doc.to_dict() == original
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
