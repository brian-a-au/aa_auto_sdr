"""Watch reads capture scope: a non-comparable family reads as such, never as "0 changes"."""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.cli.commands.watch import _SnapshotStoreAdapter
from aa_auto_sdr.pipeline.watch import _diff_summary, _event_payload, _total_changes, run_one_cycle
from aa_auto_sdr.snapshot.comparator import compare
from tests.pipeline.test_watch import _ctx, _FakeFetcher
from tests.snapshot.test_comparator_scope import FULL, _env
from tests.snapshot.test_schema_v5 import _doc


def test_summary_marks_excluded_families_not_comparable() -> None:
    diff = compare(_env(collected=FULL), _env(collected=["metrics"]))
    summary = _diff_summary(diff)
    assert _total_changes(diff) == 0
    assert summary["by_type"]["segments"] == {
        "added": 0,
        "removed": 0,
        "modified": 0,
        "comparability": "excluded",
        "suppression_reason": "not collected in target",
    }
    assert summary["by_type"]["metrics"]["comparability"] == "comparable"
    assert "suppression_reason" not in summary["by_type"]["metrics"]


def test_summary_marks_degraded_families_not_comparable() -> None:
    diff = compare(_env(collected=FULL, degraded=["classifications"]), _env(collected=FULL))
    entry = _diff_summary(diff)["by_type"]["classifications"]
    assert entry["comparability"] == "degraded"
    assert entry["suppression_reason"] == "fetch degraded"


def test_watch_cycle_with_legacy_baseline(tmp_path: Path) -> None:
    """A legacy baseline that is empty where the new capture has rows is scope-unknown."""
    legacy = _env(collected=None, populated=(), captured_at="2026-10-26T12:00:00+00:00")
    legacy["rsid"] = "demo.prod"
    legacy["components"]["report_suite"] = {"rsid": "demo.prod", "name": "Demo Production"}
    rs_dir = tmp_path / "demo.prod"
    rs_dir.mkdir()
    (rs_dir / "2026-10-26T12-00-00+00-00.json").write_text(json.dumps(legacy))
    fetcher = _FakeFetcher(rsid_to_doc={"demo.prod": _doc()})
    ctx = _ctx(fetcher=fetcher, snapshot_store=_SnapshotStoreAdapter(tmp_path))
    result = run_one_cycle(rsid="demo.prod", ctx=ctx)
    assert result.kind == "diffed", result
    payload = _event_payload(result, cycle_n=2)
    metrics = payload["summary"]["by_type"]["metrics"]
    assert metrics["comparability"] == "unknown"
    assert metrics["suppression_reason"] == "capture scope unknown (legacy snapshot)"
    assert payload["summary"]["added"] == 0
