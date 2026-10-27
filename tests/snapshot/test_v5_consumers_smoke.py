"""Consumers of snapshot envelopes run over v5 files end to end.

Rule-by-rule scope behavior lives in test_comparator_scope.py; these tests
check the CLI-facing paths (token resolution, every diff renderer, trending,
a watch cycle) over real v5 files.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.cli.commands.diff import compute_report, render_report
from aa_auto_sdr.snapshot.store import load_snapshot
from aa_auto_sdr.snapshot.trending import compute_trending

V5_FIXTURE = Path(__file__).parent.parent / "fixtures" / "snapshot_v5_metrics_only.json"


def _as_v4(env: dict) -> dict:
    out = json.loads(json.dumps(env))
    out["schema"] = "aa-sdr-snapshot/v4"
    out.pop("collected_components", None)
    return out


def _write(path: Path, env: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(env, sort_keys=True))
    return path


def test_diff_over_v5_renders_every_format(tmp_path: Path) -> None:
    v5 = json.loads(V5_FIXTURE.read_text())
    later = json.loads(V5_FIXTURE.read_text())
    later["captured_at"] = "2026-10-28T12:00:00+00:00"
    later["components"]["metrics"] = []
    a5, b5 = _write(tmp_path / "a5.json", v5), _write(tmp_path / "b5.json", later)
    report = compute_report(
        a=str(a5),
        b=str(b5),
        profile=None,
        snapshot_dir=None,
        reverse=False,
        ignore_fields=frozenset(),
        extended_fields=False,
    )
    sections = {c.component_type: c for c in report.components}
    assert [item.id for item in sections["metrics"].removed] == ["metrics/pageviews"]
    assert sections["dimensions"].comparability == "excluded"
    for fmt in ("json", "console", "markdown", "pr-comment"):
        rendered = render_report(report, fmt=fmt)
        assert "metrics/pageviews" in rendered
        assert fmt == "json" or "not collected in either snapshot" in rendered


def test_trending_over_mixed_v4_and_v5(tmp_path: Path) -> None:
    from aa_auto_sdr.snapshot.trending import WindowSpec

    rs_dir = tmp_path / "demo.prod"
    rs_dir.mkdir()
    shutil.copy(V5_FIXTURE, rs_dir / "2026-10-27T12-00-00+00-00.json")
    v4 = _as_v4(json.loads(V5_FIXTURE.read_text()))
    v4["captured_at"] = "2026-10-26T12:00:00+00:00"
    _write(rs_dir / "2026-10-26T12-00-00+00-00.json", v4)
    window = WindowSpec(
        start_at=datetime(2026, 10, 1, tzinfo=UTC),
        end_at=datetime(2026, 11, 1, tzinfo=UTC),
        duration="30d",
    )
    report = compute_trending(snapshot_dir=tmp_path, rsid="demo.prod", window=window)
    assert len(report.series) == 2
    assert report.drift.total_changes == 0


def test_watch_with_only_filtered_history_starts_a_new_baseline(tmp_path: Path) -> None:
    """Watch captures every family, so a filtered (v5) snapshot cannot be its baseline."""
    from aa_auto_sdr.cli.commands.watch import _SnapshotStoreAdapter
    from aa_auto_sdr.pipeline.watch import run_one_cycle
    from tests.pipeline.test_watch import _ctx, _FakeFetcher
    from tests.snapshot.test_schema_v5 import _doc

    store = _SnapshotStoreAdapter(snapshot_dir=tmp_path)
    rs_dir = tmp_path / "demo.prod"
    rs_dir.mkdir()
    shutil.copy(V5_FIXTURE, rs_dir / "2026-10-26T12-00-00+00-00.json")
    fetcher = _FakeFetcher(rsid_to_doc={"demo.prod": _doc(collected=("metrics",))})
    result = run_one_cycle(rsid="demo.prod", ctx=_ctx(fetcher=fetcher, snapshot_store=store))
    assert result.kind == "baseline", result
    saved = load_snapshot(result.snapshot_path)
    assert saved["schema"] == "aa-sdr-snapshot/v5"
