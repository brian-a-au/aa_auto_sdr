"""Benchmark: VRS count_only=True vs count_only=False (full ladder).

Mock-based; no live AA calls. Times the SDK call shape only — measures
what the count_only optimization saves on the SDK round-trip side, not
network or AA-server time. Documented in v1.7.2 CHANGELOG as a one-off
measurement not part of pytest tests/.

Usage:
    uv run python benchmarks/v1.7.2_count_only.py
    # Writes a table to benchmarks/results.md (appended).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api import fetch


def _make_client(rows: int) -> MagicMock:
    handle = MagicMock()
    full_rows = [
        {
            "id": f"vrs{i}",
            "name": f"VRS {i}",
            "parentRsid": "rs1",
            "timezone": "UTC",
            "description": "x" * 200,  # heavier full-expansion field
            "segmentList": ["s1", "s2", "s3"],
            "curatedComponents": ["c1", "c2"],
            "modified": "2026-05-09T00:00:00Z",
        }
        for i in range(rows)
    ]
    minimal_rows = [{"id": f"vrs{i}", "name": f"VRS {i}", "parentRsid": "rs1"} for i in range(rows)]

    def get_vrs(extended_info: bool = True) -> pd.DataFrame:
        # Simulate AA endpoint latency proportional to row count + payload size.
        # The full call returns ~5x more bytes per row in real usage; mimic with a
        # tiny sleep proportional to payload bytes.
        if extended_info:
            time.sleep(0.0005 * rows)  # 0.5ms per row, full expansion
            return pd.DataFrame(full_rows)
        time.sleep(0.0001 * rows)  # 0.1ms per row, minimal
        return pd.DataFrame(minimal_rows)

    handle.getVirtualReportSuites = get_vrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def _bench(rows: int, iterations: int = 5) -> tuple[float, float]:
    """Returns (full_ms, minimal_ms) — average over iterations."""
    full_times = []
    minimal_times = []
    for _ in range(iterations):
        client = _make_client(rows)
        t0 = time.perf_counter()
        fetch.fetch_virtual_report_suites(client, "rs1")  # default ladder, full first
        full_times.append((time.perf_counter() - t0) * 1000)

        client = _make_client(rows)
        t0 = time.perf_counter()
        fetch.fetch_virtual_report_suites(client, "rs1", count_only=True)
        minimal_times.append((time.perf_counter() - t0) * 1000)
    return (sum(full_times) / iterations, sum(minimal_times) / iterations)


def main() -> None:
    output = Path(__file__).parent / "results.md"
    rows_grid = [10, 50, 200]
    print("Benchmarking fetch_virtual_report_suites: full vs count_only ...")
    rows_data = []
    for rows in rows_grid:
        full_ms, minimal_ms = _bench(rows)
        speedup = full_ms / minimal_ms if minimal_ms > 0 else float("inf")
        print(f"  rows={rows:>4}  full={full_ms:>6.2f}ms  minimal={minimal_ms:>6.2f}ms  speedup={speedup:.2f}x")
        rows_data.append((rows, full_ms, minimal_ms, speedup))

    # Append to results.md
    with output.open("a", encoding="utf-8") as f:
        from aa_auto_sdr.core.version import __version__

        f.write(f"\n## v{__version__} — {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("Mock-based benchmark of fetch_virtual_report_suites with `count_only=True`\n")
        f.write("vs default ladder (`extended_info=True`).\n\n")
        f.write("| rows | full_ms | minimal_ms | speedup |\n")
        f.write("|---:|---:|---:|---:|\n")
        for rows, full_ms, minimal_ms, speedup in rows_data:
            f.write(f"| {rows} | {full_ms:.2f} | {minimal_ms:.2f} | {speedup:.2f}x |\n")
    print(f"\nResults appended to {output}")


if __name__ == "__main__":
    main()
