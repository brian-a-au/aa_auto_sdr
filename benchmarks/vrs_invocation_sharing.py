"""Offline complete-workload VRS benchmark; no Adobe API contact.

Run with the repository's Python environment and two source trees::

    uv run --no-sync python benchmarks/vrs_invocation_sharing.py \
        --baseline-root /tmp/baseline --candidate-root . --rounds 5

Each sample runs in a fresh subprocess, warms imports/workload once, then
measures a new invocation. Samples alternate baseline/candidate order.
SDK enumeration counts are not HTTP request counts: the real SDK paginates.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
from contextlib import redirect_stdout
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

WORKLOADS = ("batch-sequential", "batch-parallel", "stats", "inventory")


def measure(args: argparse.Namespace) -> dict:
    sys.path.insert(0, str(Path(args.source_root).resolve() / "src"))
    import pandas as pd

    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.resilience import RetryPolicy
    from aa_auto_sdr.cli.commands import inventory, stats
    from aa_auto_sdr.pipeline.batch import run_batch

    fixture = json.loads((Path(args.source_root) / "tests/fixtures/sample_rs.json").read_text())
    rsids = [f"bench.{i:03}" for i in range(args.suites)]
    suites = [{**fixture["report_suite"], "rsid": rsid, "name": rsid} for rsid in rsids]
    vrs = [
        {
            "id": f"vrs.{i:03}.{j:03}",
            "name": f"VRS {i} {j}",
            "parentRsid": rsid,
            "timezone": "UTC",
            "description": "x" * 200,
            "segmentList": ["segment1", "segment2"],
            "curatedComponents": ["pageviews"],
        }
        for i, rsid in enumerate(rsids)
        for j in range(args.vrs_per_suite)
    ]
    records = {
        "getReportSuites": suites,
        "getDimensions": fixture["dimensions"],
        "getMetrics": fixture["metrics"],
        "getSegments": fixture["segments"],
        "getCalculatedMetrics": fixture["calculated_metrics"],
        "getClassificationDatasets": fixture["classification_datasets"],
        "getVirtualReportSuites": vrs,
    }

    class Handle:
        def __init__(self) -> None:
            self.vrs_calls = 0
            self.simulated_http_pages = 0
            self.lock = threading.Lock()

        def __getattr__(self, name: str):
            if name not in records:
                raise AttributeError(name)

            def fetch(*_args, **_kwargs):
                if name == "getVirtualReportSuites":
                    with self.lock:
                        self.vrs_calls += 1
                        self.simulated_http_pages += max(1, math.ceil(len(vrs) / 1000))
                time.sleep(args.latency_ms / 1000)
                return pd.DataFrame(records[name])

            return fetch

    def workload(root: Path, handle: Handle) -> str:
        client = AaClient(handle=handle, company_id="benchmark", retry_policy=RetryPolicy(max_retries=0))
        output = io.StringIO()
        with redirect_stdout(output):
            if args.workload.startswith("batch-"):
                result = run_batch(
                    client=client,
                    rsids=rsids,
                    formats=["json"],
                    output_dir=root,
                    captured_at=datetime(2026, 1, 1, tzinfo=UTC),
                    tool_version="benchmark",
                    workers=args.workers if args.workload == "batch-parallel" else 1,
                )
                if result.failures or len(result.successes) != args.suites:
                    raise RuntimeError(f"Incomplete batch: {result.failures}")
            else:
                command = stats if args.workload == "stats" else inventory
                with (
                    patch.object(command.credentials, "resolve", return_value=object()),
                    patch.object(command.AaClient, "from_credentials", return_value=client),
                ):
                    code = command.run(rsids=rsids, profile=None, format_name="json")
                if code != 0:
                    raise RuntimeError(f"Command failed: {code}: {output.getvalue()}")
        return output.getvalue()

    # Keep imports and one warm run outside allocation/time measurements.
    with tempfile.TemporaryDirectory(prefix="aa-vrs-warm-") as folder:
        workload(Path(folder), Handle())
    handle = Handle()
    with tempfile.TemporaryDirectory(prefix="aa-vrs-measure-") as folder:
        root = Path(folder)
        tracemalloc.start()
        started = time.perf_counter()
        stdout = workload(root, handle)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if args.workload.startswith("batch-"):
            payload = {p.name: json.loads(p.read_text()) for p in sorted(root.glob("*.json"))}
            if len(payload) != args.suites:
                raise RuntimeError("Missing batch artifacts")
        else:
            payload = json.loads(stdout)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {
        "seconds": elapsed,
        "peak_bytes": peak,
        "sdk_vrs_calls": handle.vrs_calls,
        "simulated_http_pages": handle.simulated_http_pages,
        "output_sha256": digest,
    }


def source_identity(root: Path) -> dict[str, str]:
    """Hash the source and lockfile used by a sampled subprocess."""
    source = root / "src" / "aa_auto_sdr"
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    lockfile = root / "uv.lock"
    return {
        "source_sha256": digest.hexdigest(),
        "lock_sha256": hashlib.sha256(lockfile.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--candidate-root", type=Path, default=Path.cwd())
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--suites", type=int, default=50)
    parser.add_argument("--vrs-per-suite", type=int, default=20)
    parser.add_argument("--latency-ms", type=float, default=5.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--workload", choices=WORKLOADS, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.source_root:
        print(json.dumps(measure(args), sort_keys=True))
        return
    if not args.baseline_root or min(args.rounds, args.suites, args.vrs_per_suite, args.workers) < 1:
        parser.error("provide --baseline-root and positive workload sizes")
    if args.latency_ms < 0:
        parser.error("--latency-ms must be nonnegative")
    roots = {"baseline": args.baseline_root.resolve(), "candidate": args.candidate_root.resolve()}

    def sample(variant: str, workload: str) -> dict:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--source-root",
            str(roots[variant]),
            "--workload",
            workload,
            "--suites",
            str(args.suites),
            "--vrs-per-suite",
            str(args.vrs_per_suite),
            "--latency-ms",
            str(args.latency_ms),
            "--workers",
            str(args.workers),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=os.environ.copy())
        return json.loads(result.stdout)

    report = {
        "python": sys.version,
        "dependencies": {name: version(name) for name in ("aanalytics2", "pandas", "numpy")},
        "roots": {k: str(v) for k, v in roots.items()},
        "source_identity": {k: source_identity(v) for k, v in roots.items()},
        "suites": args.suites,
        "vrs_per_suite": args.vrs_per_suite,
        "latency_ms_per_sdk_call": args.latency_ms,
        "parallel_workers": args.workers,
        "rounds": args.rounds,
        "workloads": {},
        "scope": "Synthetic SDK latency; complete workloads; peak Python allocation, not RSS or live API speedup. HTTP pages are simulated at 1000 VRS rows per page and differ from SDK enumerations.",
    }
    for workload in WORKLOADS:
        samples = {variant: [] for variant in roots}
        expected_digest = None
        # Semantic check precedes the alternating recorded measurements.
        for variant in roots:
            value = sample(variant, workload)
            if expected_digest is None:
                expected_digest = value["output_sha256"]
            if value["output_sha256"] != expected_digest:
                raise RuntimeError(f"Output mismatch: {workload} {variant}")
        for index in range(args.rounds):
            order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
            for variant in order:
                value = sample(variant, workload)
                if value["output_sha256"] != expected_digest:
                    raise RuntimeError(f"Output mismatch: {workload} {variant}")
                samples[variant].append(value)
        summary = {}
        for variant, values in samples.items():
            summary[variant] = {
                "median_seconds": statistics.median(v["seconds"] for v in values),
                "min_seconds": min(v["seconds"] for v in values),
                "max_seconds": max(v["seconds"] for v in values),
                "median_peak_bytes": statistics.median(v["peak_bytes"] for v in values),
                "sdk_vrs_calls": sorted({v["sdk_vrs_calls"] for v in values}),
                "simulated_http_pages": sorted({v["simulated_http_pages"] for v in values}),
            }
        report["workloads"][workload] = {"samples": samples, "summary": summary}
        print(f"{workload}: {summary}", file=sys.stderr, flush=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
