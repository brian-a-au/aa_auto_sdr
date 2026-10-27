"""Covering baselines: compare against the newest earlier snapshot whose scope covers this one.

A filtered snapshot between two full ones must not hide changes to the
families it left out. Watch, --compare-with-prev, and trending skip earlier
snapshots that did not collect every family the current capture collected.
Snapshots without scope (legacy) count as full captures. Explicit --diff
tokens stay literal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.snapshot.baseline import covers
from aa_auto_sdr.snapshot.resolver import resolve_covering_pair
from tests.snapshot.test_comparator_scope import FULL, _env

T1, T2, T3 = "2026-10-25T12:00:00+00:00", "2026-10-26T12:00:00+00:00", "2026-10-27T12:00:00+00:00"


def _write(snapshot_dir: Path, env: dict[str, Any]) -> Path:
    rs_dir = snapshot_dir / env["rsid"]
    rs_dir.mkdir(parents=True, exist_ok=True)
    path = rs_dir / (env["captured_at"].replace(":", "-") + ".json")
    path.write_text(json.dumps(env, sort_keys=True))
    return path


def _snap(collected: list[str] | None, ts: str, **kw: Any) -> dict[str, Any]:
    return _env(collected=collected, captured_at=ts, **kw)


@pytest.mark.parametrize(
    ("candidate", "target", "expected"),
    [
        (FULL, FULL, True),
        (None, FULL, True),
        (FULL, ["metrics"], True),
        (["metrics"], ["metrics"], True),
        (["metrics", "dimensions"], ["metrics"], True),
        (["metrics"], FULL, False),
        (["metrics"], None, False),
        (["dimensions"], ["metrics"], False),
        (None, None, True),
    ],
)
def test_covers(candidate, target, expected) -> None:
    assert covers(candidate, target) is expected


def test_pair_skips_a_filtered_snapshot_between_full_ones(tmp_path: Path) -> None:
    a = _write(tmp_path, _snap(FULL, T1))
    _write(tmp_path, _snap(["metrics"], T2))
    b = _write(tmp_path, _snap(FULL, T3))
    pair = resolve_covering_pair("rs1", snapshot_dir=tmp_path)
    assert (pair.baseline_path, pair.target_path) == (a, b)
    assert pair.skipped == (T2,)


def test_pair_for_a_filtered_target_uses_the_newest_covering_snapshot(tmp_path: Path) -> None:
    a = _write(tmp_path, _snap(FULL, T1))
    _write(tmp_path, _snap(["dimensions"], T2))
    b = _write(tmp_path, _snap(["metrics"], T3))
    pair = resolve_covering_pair("rs1", snapshot_dir=tmp_path)
    assert (pair.baseline_path, pair.skipped) == (a, (T2,))
    assert pair.target_path == b


def test_pair_of_full_snapshots_is_the_two_newest(tmp_path: Path) -> None:
    _write(tmp_path, _snap(FULL, T1))
    a = _write(tmp_path, _snap(None, T2))
    b = _write(tmp_path, _snap(FULL, T3))
    pair = resolve_covering_pair("rs1", snapshot_dir=tmp_path)
    assert (pair.baseline_path, pair.target_path, pair.skipped) == (a, b, ())


def test_pair_without_a_covering_snapshot_raises(tmp_path: Path) -> None:
    _write(tmp_path, _snap(["metrics"], T1))
    _write(tmp_path, _snap(FULL, T2))
    with pytest.raises(SnapshotResolveError, match="covers"):
        resolve_covering_pair("rs1", snapshot_dir=tmp_path)


def test_pair_with_one_snapshot_raises(tmp_path: Path) -> None:
    _write(tmp_path, _snap(FULL, T1))
    with pytest.raises(SnapshotResolveError, match="at least two"):
        resolve_covering_pair("rs1", snapshot_dir=tmp_path)


def test_compare_with_prev_reports_changes_hidden_by_a_filtered_snapshot(tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import compare_with_prev

    _write(tmp_path, _snap(FULL, T1))
    _write(tmp_path, _snap(["metrics"], T2))
    _write(tmp_path, _snap(FULL, T3, populated=("metrics",)))
    rc = compare_with_prev.run(
        rsids=["rs1"],
        profile=None,
        snapshot_dir=tmp_path,
        format_name="json",
        output="-",
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["a_captured_at"] == T1
    assert payload["baseline_skipped"] == [T2]
    dims = next(c for c in payload["components"] if c["component_type"] == "dimensions")
    assert dims["comparability"] == "comparable"
    assert [item["id"] for item in dims["removed"]] == ["variables/evar1"]


def test_explicit_previous_token_stays_literal(tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands.diff import compute_report

    _write(tmp_path, _snap(FULL, T1))
    _write(tmp_path, _snap(["metrics"], T2))
    _write(tmp_path, _snap(FULL, T3))
    report = compute_report(
        a="rs1@previous",
        b="rs1@latest",
        profile=None,
        snapshot_dir=tmp_path,
        reverse=False,
        ignore_fields=frozenset(),
        extended_fields=False,
    )
    assert report.a_captured_at == T2
    assert report.baseline_skipped == []


def test_watch_baseline_skips_filtered_history(tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands.watch import _SnapshotStoreAdapter

    _write(tmp_path, _snap(FULL, T1))
    _write(tmp_path, _snap(["metrics"], T2))
    choice = _SnapshotStoreAdapter(tmp_path).baseline("rs1")
    assert choice.envelope["captured_at"] == T1
    assert choice.skipped == (T2,)
    assert _SnapshotStoreAdapter(tmp_path).latest("rs1")["captured_at"] == T1


def test_watch_event_names_its_baseline(tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands.watch import _SnapshotStoreAdapter
    from aa_auto_sdr.pipeline.watch import _event_payload, run_one_cycle
    from tests.pipeline.test_watch import _ctx, _FakeFetcher
    from tests.snapshot.test_schema_v5 import _doc

    full = _snap(FULL, T1)
    full["rsid"] = "demo.prod"
    full["components"]["report_suite"] = {"rsid": "demo.prod", "name": "Demo Production"}
    filtered = json.loads(json.dumps(full))
    filtered.update(captured_at=T2, collected_components=["metrics"], schema="aa-sdr-snapshot/v5")
    _write(tmp_path, full)
    _write(tmp_path, filtered)
    ctx = _ctx(fetcher=_FakeFetcher(rsid_to_doc={"demo.prod": _doc()}), snapshot_store=_SnapshotStoreAdapter(tmp_path))
    result = run_one_cycle(rsid="demo.prod", ctx=ctx)
    assert result.kind == "diffed", result
    assert result.diff.a_captured_at == T1
    assert _event_payload(result, cycle_n=1)["baseline"] == {"captured_at": T1, "skipped": [T2]}


def test_trending_pairs_use_covering_baselines(tmp_path: Path) -> None:
    from aa_auto_sdr.snapshot.trending import WindowSpec, compute_trending

    _write(tmp_path, _snap(FULL, T1))
    _write(tmp_path, _snap(["metrics"], T2))
    _write(tmp_path, _snap(FULL, T3, populated=("metrics",)))
    window = WindowSpec(
        duration="30d", start_at=datetime(2026, 10, 1, tzinfo=UTC), end_at=datetime(2026, 11, 1, tzinfo=UTC)
    )
    report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window)
    t1, t2, t3 = report.series
    assert t1.baseline_captured_at is None
    assert t2.baseline_captured_at == datetime.fromisoformat(T1)
    assert t3.baseline_captured_at == datetime.fromisoformat(T1)
    assert t3.delta_by_type["dimensions"].removed == 1
    assert report.drift.total_changes == 5


def test_trending_point_without_a_covering_baseline_has_no_delta(tmp_path: Path) -> None:
    from aa_auto_sdr.snapshot.trending import WindowSpec, compute_trending

    _write(tmp_path, _snap(["metrics"], T1))
    _write(tmp_path, _snap(FULL, T2))
    window = WindowSpec(
        duration="30d", start_at=datetime(2026, 10, 1, tzinfo=UTC), end_at=datetime(2026, 11, 1, tzinfo=UTC)
    )
    second = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window).series[1]
    assert second.baseline_captured_at is None
    assert second.delta_by_type is None


@pytest.mark.parametrize(
    ("scopes", "keep_last", "deleted"),
    [
        ([FULL, ["metrics"]], 1, []),
        ([FULL, FULL, ["metrics"]], 1, [0]),
        ([None, ["metrics"], ["metrics"]], 1, [1]),
        ([FULL, FULL], 1, [0]),
    ],
    ids=["protects-only-full", "protects-newest-full", "legacy-counts-as-full", "plain"],
)
def test_keep_last_never_prunes_the_newest_full_capture(tmp_path: Path, scopes, keep_last, deleted) -> None:
    from aa_auto_sdr.snapshot.retention import RetentionPolicy
    from aa_auto_sdr.snapshot.store import prune_snapshots

    stamps = [f"2026-10-2{i}T12:00:00+00:00" for i in range(len(scopes))]
    paths = [_write(tmp_path, _snap(scope, ts)) for scope, ts in zip(scopes, stamps, strict=True)]
    removed = prune_snapshots(tmp_path, RetentionPolicy(keep_last=keep_last), rsid="rs1")
    assert removed == [paths[i] for i in deleted]
    assert all(p.exists() for i, p in enumerate(paths) if i not in deleted)
