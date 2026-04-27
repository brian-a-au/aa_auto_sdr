"""RunSummary dataclass + JSON serialization."""

from __future__ import annotations

import json

from aa_auto_sdr.core.run_summary import PerRsidResult, RunSummary


def test_per_rsid_result_minimal() -> None:
    r = PerRsidResult(rsid="rs1", name="RS One", succeeded=True)
    assert r.rsid == "rs1"
    assert r.formats == []
    assert r.snapshot_path is None
    assert r.error is None


def test_run_summary_to_dict_round_trip() -> None:
    summary = RunSummary(
        started_at="2026-04-26T10:00:00+00:00",
        finished_at="2026-04-26T10:00:05+00:00",
        duration_seconds=5.0,
        tool_version="1.2.0",
        profile="prod",
        rsids=[
            PerRsidResult(
                rsid="rs1",
                name="RS One",
                succeeded=True,
                formats=["excel", "json"],
                output_paths=["/tmp/rs1.xlsx", "/tmp/rs1.json"],
            ),
        ],
    )
    d = summary.to_dict()
    serialized = json.dumps(d, sort_keys=True)
    parsed = json.loads(serialized)
    assert parsed["tool_version"] == "1.2.0"
    assert parsed["rsids"][0]["rsid"] == "rs1"
    assert parsed["rsids"][0]["formats"] == ["excel", "json"]


def test_run_summary_with_failure() -> None:
    summary = RunSummary(
        started_at="t0",
        finished_at="t1",
        duration_seconds=1.0,
        tool_version="1.2.0",
        profile=None,
        rsids=[
            PerRsidResult(rsid="bad", name=None, succeeded=False, error="not found"),
        ],
    )
    d = summary.to_dict()
    assert d["rsids"][0]["succeeded"] is False
    assert d["rsids"][0]["error"] == "not found"


def test_run_summary_includes_timings() -> None:
    summary = RunSummary(
        started_at="t0",
        finished_at="t1",
        duration_seconds=1.0,
        tool_version="1.2.0",
        profile=None,
        rsids=[],
        timings=[("auth", 0.5), ("fetch", 0.3)],
    )
    d = summary.to_dict()
    assert d["timings"] == [["auth", 0.5], ["fetch", 0.3]]
