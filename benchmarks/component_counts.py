"""Offline U6 complete-command/count and full-fetch control measurements.

Uses the existing VRS fixture shape, but honors format=raw for segment/calculated
metric SDK calls. This correction applies to BOTH source roots, not earlier arc
records. No HTTP. Imports, fixtures, auth and one warm operation are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import time
import tracemalloc
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from vrs_invocation_sharing import source_identity


def measure(args):
    sys.path.insert(0, str(args.source_root / "src"))
    import pandas as pd

    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.resilience import RetryPolicy
    from aa_auto_sdr.cli.commands import stats

    rich = args.case != "stats-small"
    suites_count = 20 if rich and args.case != "full-rich" else 1
    fixture = json.loads((args.source_root / "tests/fixtures/sample_rs.json").read_text())
    if rich:
        for name, size in [("dimensions", 200), ("metrics", 200), ("segments", 1000), ("calculated_metrics", 200)]:
            fixture[name] = [{**fixture[name][i % len(fixture[name])], "id": f"{name}.{i}"} for i in range(size)]
    suites = [{**fixture["report_suite"], "rsid": f"bench.{i}", "name": f"bench.{i}"} for i in range(suites_count)]
    by_id = {row["rsid"]: row for row in suites}
    records = dict(
        zip(
            ["getDimensions", "getMetrics", "getSegments", "getCalculatedMetrics", "getClassificationDatasets"],
            [
                fixture[k]
                for k in ["dimensions", "metrics", "segments", "calculated_metrics", "classification_datasets"]
            ],
            strict=True,
        )
    )
    records["getVirtualReportSuites"] = [
        {"id": f"vrs.{rs['rsid']}.{j}", "parentRsid": rs["rsid"], "name": f"VRS {j}", "segmentList": ["s1"]}
        for rs in suites
        for j in range(10)
    ]

    class Handle:
        def __init__(self):
            self.calls = {}

        def __getattr__(self, name):
            def call(**kwargs):
                self.calls[name] = self.calls.get(name, 0) + 1
                if name == "getReportSuites":
                    requested = kwargs.get("rsid_list")
                    if isinstance(requested, str):
                        requested = [requested]
                    rows = suites if requested is None else [by_id[r] for r in requested]
                else:
                    rows = records[name]
                return rows if kwargs.get("format") == "raw" else pd.DataFrame(rows)

            return call

    handle = Handle()
    client = AaClient(handle=handle, company_id="benchmark", retry_policy=RetryPolicy(max_retries=0))

    def operation():
        if args.case == "full-rich":
            return {
                name: getattr(fetch, "fetch_" + name)(client, "bench.0")
                for name in ["dimensions", "metrics", "segments", "calculated_metrics"]
            }
        stdout = io.StringIO()
        with (
            redirect_stdout(stdout),
            patch.object(stats.credentials, "resolve", return_value=object()),
            patch.object(stats.AaClient, "from_credentials", return_value=client),
        ):
            codes = [stats.run(rsids=list(by_id), profile=None, format_name="json")]
        assert codes == [0] * len(codes), codes
        return stdout.getvalue()

    operation()
    handle.calls.clear()
    if args.allocation:
        tracemalloc.start()
    started = time.perf_counter()
    result = operation()
    elapsed = time.perf_counter() - started
    peak = tracemalloc.get_traced_memory()[1] if args.allocation else None
    if args.allocation:
        tracemalloc.stop()
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    if args.case == "full-rich":
        result = {name: [asdict(row) for row in rows] for name, rows in result.items()}
    else:
        result = json.loads(result)
    return {
        "seconds": elapsed,
        "peak_bytes": peak,
        "process_peak_rss_bytes": rss,
        "sdk_calls": handle.calls,
        "output_sha256": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--candidate-root", type=Path, default=Path.cwd())
    parser.add_argument("--case", choices=["stats-rich", "stats-small", "full-rich"], required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--allocation", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.source_root:
        print(json.dumps(measure(args), sort_keys=True))
        return
    assert args.baseline_root
    assert args.output
    roots = {"baseline": args.baseline_root.resolve(), "candidate": args.candidate_root.resolve()}

    def sample(variant, allocation=False):
        cmd = [sys.executable, str(Path(__file__).resolve()), "--source-root", str(roots[variant]), "--case", args.case]
        if allocation:
            cmd.append("--allocation")
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)

    pairs = []
    for i in range(7):
        pair = {}
        for variant in ["baseline", "candidate"] if i % 2 == 0 else ["candidate", "baseline"]:
            pair[variant] = sample(variant)
        pairs.append(pair)
    allocations = {variant: sample(variant, True) for variant in roots}
    samples = [s for pair in pairs for s in pair.values()] + list(allocations.values())
    assert len({s["output_sha256"] for s in samples}) == 1
    assert all(s["sdk_calls"] == samples[0]["sdk_calls"] for s in samples)
    report = {
        "case": args.case,
        "python": sys.version,
        "sources": {name: source_identity(root) for name, root in roots.items()},
        "wall_pairs": pairs,
        "allocation": allocations,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
