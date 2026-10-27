"""Report-suite setting changes are counted, shown, and trigger watch on their own.

`settings_changes` counts changed report-suite fields (one per field). It stays
separate from component churn: it never enters component totals, the watch
threshold, or the diff warn threshold, but any setting change emits a watch
change event and makes the cycle eligible for publication.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from aa_auto_sdr.cli.commands.diff import render_report, report_exit_code
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.pipeline.watch import CycleResult, _diff_summary, _should_emit, _should_publish
from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.git import generate_commit_message
from aa_auto_sdr.snapshot.trending import WindowSpec, compute_trending
from tests.snapshot.test_comparator_scope import FULL, _env


def _with_settings(env: dict[str, Any], **settings: Any) -> dict[str, Any]:
    env["components"]["report_suite"] = {**env["components"]["report_suite"], **settings}
    return env


def _pair(field: str, before: str, after: str, **kw: Any) -> tuple[dict, dict]:
    a = _with_settings(_env(collected=FULL, **kw), **{field: before})
    b = _with_settings(_env(collected=FULL, **kw), **{field: after})
    return a, b


SETTING_CASES = [("currency", "USD", "EUR"), ("timezone", "UTC", "US/Pacific")]


def _diffed(diff) -> CycleResult:
    now = datetime(2026, 10, 27, tzinfo=UTC)
    return CycleResult.diffed(rsid="rs1", snapshot_path=Path("/tmp/x.json"), diff=diff, started_at=now, ended_at=now)


@pytest.mark.parametrize(("field", "before", "after"), SETTING_CASES)
def test_one_setting_change_counts_once(field: str, before: str, after: str) -> None:
    report = compare(*_pair(field, before, after))
    assert report.settings_changes == 1
    assert all(not (c.added or c.removed or c.modified) for c in report.components)


def test_no_setting_change_counts_zero() -> None:
    assert compare(_env(collected=FULL), _env(collected=FULL)).settings_changes == 0


def test_diff_json_carries_settings_changes_even_in_summary_mode() -> None:
    report = compare(*_pair("currency", "USD", "EUR"))
    for summary in (False, True):
        payload = json.loads(render_report(report, fmt="json", summary=summary))
        assert payload["settings_changes"] == 1


def test_diff_warn_threshold_stays_component_only() -> None:
    report = compare(*_pair("currency", "USD", "EUR"))
    assert report_exit_code(report, warn_threshold=1) == ExitCode.OK.value


@pytest.mark.parametrize("fmt", ["console", "markdown", "pr-comment"])
@pytest.mark.parametrize("summary", [False, True])
def test_every_renderer_shows_setting_changes(fmt: str, summary: bool) -> None:
    rendered = render_report(compare(*_pair("currency", "USD", "EUR")), fmt=fmt, summary=summary)
    assert "currency" in rendered
    if not summary:
        assert "EUR" in rendered


@pytest.mark.parametrize(("field", "before", "after"), SETTING_CASES)
def test_watch_emits_and_publishes_on_a_setting_change_above_threshold(field: str, before: str, after: str) -> None:
    result = _diffed(compare(*_pair(field, before, after)))
    assert _should_emit(result, threshold=50)
    assert _should_publish(result, threshold=50)
    assert _diff_summary(result.diff)["settings_changes"] == 1


def test_watch_unchanged_cycle_still_quiet() -> None:
    result = _diffed(compare(_env(collected=FULL), _env(collected=FULL)))
    assert not _should_emit(result, threshold=1)
    assert not _should_publish(result, threshold=1)
    assert _diff_summary(result.diff)["settings_changes"] == 0


def test_watch_setting_change_with_suppressed_sections_still_triggers() -> None:
    a = _with_settings(_env(collected=FULL, degraded=["classifications"]), currency="USD")
    b = _with_settings(_env(collected=["metrics"]), currency="EUR")
    result = _diffed(compare(a, b))
    assert _should_emit(result, threshold=1)
    summary = _diff_summary(result.diff)
    assert summary["added"] == summary["removed"] == summary["modified"] == 0


def test_watch_commit_body_lists_settings_changes() -> None:
    summary = _diff_summary(compare(*_pair("timezone", "UTC", "US/Pacific")))
    msg = generate_commit_message(rsid="rs1", captured_at="2026-10-27T00:00:00Z", change_summary=summary)
    assert "settings:   1 changed" in msg


def test_trending_counts_settings_separately(tmp_path: Path) -> None:
    from aa_auto_sdr.output.trending_renderers.console import render_console
    from aa_auto_sdr.output.trending_renderers.json import render_json
    from aa_auto_sdr.output.trending_renderers.markdown import render_markdown

    rs_dir = tmp_path / "rs1"
    rs_dir.mkdir()
    for ts, currency in (("2026-10-25T12:00:00+00:00", "USD"), ("2026-10-26T12:00:00+00:00", "EUR")):
        env = _with_settings(_env(collected=FULL, captured_at=ts), currency=currency)
        (rs_dir / (ts.replace(":", "-") + ".json")).write_text(json.dumps(env))
    window = WindowSpec(
        duration="30d",
        start_at=datetime(2026, 10, 1, tzinfo=UTC),
        end_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    report = compute_trending(snapshot_dir=tmp_path, rsid="rs1", window=window)
    assert report.series[0].settings_changes is None
    assert report.series[1].settings_changes == 1
    assert report.drift.settings_changes == 1
    assert report.drift.total_changes == 0
    assert json.loads(render_json([report]))["drift"]["settings_changes"] == 1
    for text in (render_console([report]), render_markdown([report])):
        assert "Settings changes" in text
        assert "Δset" in text
    md_rows = [line for line in render_markdown([report]).splitlines() if line.startswith("| 2026-10-26")]
    assert md_rows[0].rstrip(" |").endswith("| 1")


def test_pr_comment_settings_table_escapes_and_caps_values() -> None:
    a, b = _pair("name", "Old", "New | " + "x" * 500)
    rendered = render_report(compare(a, b), fmt="pr-comment")
    row = next(line for line in rendered.splitlines() if line.startswith("| `name`"))
    assert "New \\| " in row
    assert "x" * 500 not in row
