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
