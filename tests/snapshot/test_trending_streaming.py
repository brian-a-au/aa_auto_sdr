"""Trending loads each in-window snapshot exactly once, in order.

`compute_trending` must stream: load snapshot N, diff it against snapshot
N-1, then move on — never hold more than two envelopes (`prev`/`last`)
resident. Peak residency itself isn't observable from a unit test, but its
consequence is: each snapshot is loaded exactly once (`load_calls == paths`)
and loads/diffs interleave rather than all-loads-then-all-diffs. An eager
`[load_snapshot(p) for p in matching]` front-load would produce
load, load, load, compare, compare — this test fails against that shape and
passes once the loop streams.
"""

from __future__ import annotations

import datetime as dt

from aa_auto_sdr.snapshot import trending


def test_trending_loads_each_snapshot_once(monkeypatch, tmp_path):
    paths = [tmp_path / f"2026-01-0{i}.json" for i in (1, 2, 3)]
    monkeypatch.setattr(trending, "list_snapshots", lambda _d, **_kwargs: paths)
    monkeypatch.setattr(trending, "_path_in_window", lambda _p, _w: True)

    load_calls: list = []
    events: list[str] = []

    def fake_load(p):
        load_calls.append(p)
        events.append(f"load:{p.name}")
        return {"p": str(p)}

    def fake_compare(**_kwargs):
        events.append("compare")
        return type("D", (), {"components": []})()

    monkeypatch.setattr(trending, "load_snapshot", fake_load)
    # Stub the per-snapshot helpers so only the load loop is under test.
    monkeypatch.setattr(trending, "compare", fake_compare)
    monkeypatch.setattr(trending, "_to_snapshot_point", lambda snap, _delta: snap)
    monkeypatch.setattr(
        trending,
        "_compute_drift_summary",
        lambda _series: trending.DriftSummary(total_changes=0, volatility_score=0.0, most_active_component_type=None),
    )
    monkeypatch.setattr(trending, "_name_from_envelope", lambda _env: "RS")

    report = trending.compute_trending(snapshot_dir=tmp_path, rsid="rs", window=dt.timedelta(days=30))
    assert len(report.series) == 3
    assert load_calls == paths  # each path loaded exactly once, in order

    # Interleaved load/compare proves the sliding window: snapshot 1 is
    # diffed against snapshot 2 before snapshot 3 is ever loaded, so at most
    # two envelopes (prev, last) are resident at a time.
    assert events == [
        "load:2026-01-01.json",
        "load:2026-01-02.json",
        "compare",
        "load:2026-01-03.json",
        "compare",
    ]
