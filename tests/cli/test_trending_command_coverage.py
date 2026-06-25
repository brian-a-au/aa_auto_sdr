"""--trending-window handler coverage — cli/commands/trending.py.

Exercises the format-validation, render-dispatch, file-output, and
snapshot-dir resolution paths directly via ``trending.run`` with
``compute_trending`` patched to return constructed reports (no AA API,
no filesystem snapshots).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from aa_auto_sdr.cli.commands import trending as trending_cmd
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.snapshot.trending import (
    ComponentCounts,
    DriftSummary,
    SnapshotPoint,
    TrendingReport,
    WindowSpec,
)

_COMPONENT_TYPES = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
)


def _make_report(rsid: str, *, empty: bool = False) -> TrendingReport:
    """Build a TrendingReport the renderers can consume.

    `empty=True` yields a report with no series (the no-snapshots case);
    otherwise a single-snapshot series with a zero-drift summary.
    """
    window = WindowSpec(
        duration="30d",
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    drift = DriftSummary(
        total_changes=0,
        volatility_score=0.0,
        most_active_component_type=None,
        churn_by_component_type=dict.fromkeys(_COMPONENT_TYPES, 0),
    )
    series: list[SnapshotPoint] = []
    if not empty:
        series = [
            SnapshotPoint(
                captured_at=datetime(2026, 5, 1, tzinfo=UTC),
                tool_version="1.21.0",
                counts=ComponentCounts(dimensions=10, metrics=5),
                delta_by_type=None,
            ),
        ]
    return TrendingReport(rsid=rsid, name=rsid.upper(), window=window, series=series, drift=drift)


class TestFormatValidation:
    def test_invalid_format_returns_output_exit(self, tmp_path: Path, capsys) -> None:
        exit_code = trending_cmd.run(
            rsids=["rs1"],
            duration="30d",
            snapshot_dir=tmp_path,
            profile=None,
            format_name="xml",
            output=None,
        )
        assert exit_code == ExitCode.OUTPUT.value
        out = capsys.readouterr().out
        assert "format must be" in out
        assert "xml" in out


class TestRenderDispatch:
    def test_json_format_renders_to_stdout(self, tmp_path: Path, capsys) -> None:
        with patch.object(trending_cmd, "compute_trending", return_value=_make_report("rs1")):
            exit_code = trending_cmd.run(
                rsids=["rs1"],
                duration="30d",
                snapshot_dir=tmp_path,
                profile=None,
                format_name="json",
                output=None,
            )
        assert exit_code == ExitCode.OK.value
        payload = json.loads(capsys.readouterr().out)
        assert payload["schema"] == "aa-trending/v1"
        assert payload["rsid"] == "rs1"

    def test_markdown_format_renders_to_stdout(self, tmp_path: Path, capsys) -> None:
        with patch.object(trending_cmd, "compute_trending", return_value=_make_report("rs1")):
            exit_code = trending_cmd.run(
                rsids=["rs1"],
                duration="30d",
                snapshot_dir=tmp_path,
                profile=None,
                format_name="markdown",
                output="-",
            )
        assert exit_code == ExitCode.OK.value
        assert capsys.readouterr().out.startswith("# Trending: rs1")


class TestFileOutput:
    def test_console_output_to_file_writes_and_returns_ok(self, tmp_path: Path) -> None:
        out_file = tmp_path / "trend.txt"
        with patch.object(trending_cmd, "compute_trending", return_value=_make_report("rs1")):
            exit_code = trending_cmd.run(
                rsids=["rs1"],
                duration="30d",
                snapshot_dir=tmp_path,
                profile=None,
                format_name="console",
                output=str(out_file),
            )
        assert exit_code == ExitCode.OK.value
        content = out_file.read_text(encoding="utf-8")
        assert "TRENDING WINDOW (rs1" in content


class TestResolveSnapshotDir:
    def test_profile_builds_orgs_snapshots_path(self) -> None:
        result = trending_cmd._resolve_snapshot_dir(snapshot_dir=None, profile="prod")
        assert result is not None
        assert result.name == "snapshots"
        assert "orgs" in result.parts
        assert "prod" in result.parts
