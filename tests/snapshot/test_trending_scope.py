"""Trending carries comparability per family so excluded families never read as zero churn."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.output.trending_renderers.console import render_console
from aa_auto_sdr.output.trending_renderers.json import render_json
from aa_auto_sdr.output.trending_renderers.markdown import render_markdown
from aa_auto_sdr.snapshot.trending import WindowSpec, compute_trending
from tests.snapshot.test_comparator_scope import FULL, _env


def _report(tmp_path: Path):
    rs_dir = tmp_path / "rs1"
    rs_dir.mkdir()
    pairs = [
        ("2026-10-25T12:00:00+00:00", _env(collected=FULL, captured_at="2026-10-25T12:00:00+00:00")),
        ("2026-10-26T12:00:00+00:00", _env(collected=["metrics"], captured_at="2026-10-26T12:00:00+00:00")),
    ]
    for ts, env in pairs:
        (rs_dir / (ts.replace(":", "-") + ".json")).write_text(json.dumps(env))
    window = WindowSpec(
        duration="30d",
        start_at=datetime(2026, 10, 1, tzinfo=UTC),
        end_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    return compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window)


def test_trending_mixing_v4_and_v5_has_no_false_churn(tmp_path: Path) -> None:
    report = _report(tmp_path)
    assert report.drift.total_changes == 0
    delta = report.series[1].delta_by_type
    assert delta["segments"].comparability == "excluded"
    assert delta["segments"].suppression_reason == "not collected in target"
    assert delta["metrics"].comparability == "comparable"


def test_trending_json_carries_comparability(tmp_path: Path) -> None:
    payload = json.loads(render_json([_report(tmp_path)]))
    assert payload["series"][1]["delta_by_type"]["segments"]["comparability"] == "excluded"


def test_trending_markdown_and_console_name_non_comparable_families(tmp_path: Path) -> None:
    report = _report(tmp_path)
    for text in (render_markdown([report]), render_console([report])):
        assert "not comparable" in text.lower()
        assert "not collected in target" in text
        assert "segments" in text


_NEW_DIM = {"id": "variables/evar2", "name": "eVar 2"}
_WINDOW = WindowSpec(
    duration="30d",
    start_at=datetime(2026, 10, 1, tzinfo=UTC),
    end_at=datetime(2026, 11, 1, tzinfo=UTC),
)


def _write_series(tmp_path: Path, specs: list[tuple[str, list[str], bool]]) -> None:
    rs = tmp_path / "rs1"
    rs.mkdir()
    for ts, collected, extra in specs:
        e = _env(collected=collected, captured_at=ts)
        if extra:
            e["components"]["dimensions"].append(dict(_NEW_DIM))
        (rs / (ts.replace(":", "-") + ".json")).write_text(json.dumps(e))


def test_mixed_scope_series_counts_change_once(tmp_path: Path) -> None:
    # full A, dims-only B, dims-only C (+1 dimension), full D (still has it)
    _write_series(
        tmp_path,
        [
            ("2026-10-24T12:00:00+00:00", FULL, False),
            ("2026-10-25T12:00:00+00:00", ["dimensions"], False),
            ("2026-10-26T12:00:00+00:00", ["dimensions"], True),
            ("2026-10-27T12:00:00+00:00", FULL, True),
        ],
    )
    report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=_WINDOW)
    assert report.drift.total_changes == 1
    assert report.drift.churn_by_component_type["dimensions"] == 1


def test_all_full_series_drift_unchanged(tmp_path: Path) -> None:
    _write_series(
        tmp_path,
        [
            ("2026-10-24T12:00:00+00:00", FULL, False),
            ("2026-10-25T12:00:00+00:00", FULL, True),
            ("2026-10-26T12:00:00+00:00", FULL, False),
            ("2026-10-27T12:00:00+00:00", FULL, True),
        ],
    )
    report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=_WINDOW)
    assert report.drift.total_changes == 3
    assert report.drift.volatility_score == 0.167  # value observed before the fix
