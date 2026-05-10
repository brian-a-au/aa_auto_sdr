"""CLI argparse for v1.13.0 trending flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from aa_auto_sdr.cli.parser import build_parser


class TestTrendingWindowArgparse:
    def test_default_none(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.trending_window is None

    def test_accepts_duration(self) -> None:
        ns = build_parser().parse_args(["rs1", "--trending-window", "30d"])
        assert ns.trending_window == "30d"

    def test_accepts_hours(self) -> None:
        ns = build_parser().parse_args(["rs1", "--trending-window", "12h"])
        assert ns.trending_window == "12h"

    def test_accepts_weeks(self) -> None:
        ns = build_parser().parse_args(["rs1", "--trending-window", "4w"])
        assert ns.trending_window == "4w"

    def test_value_validation_deferred_to_handler(self) -> None:
        """Argparse accepts any string; the handler validates via parse_duration().
        This keeps argparse error messages consistent with retention's grammar."""
        ns = build_parser().parse_args(["rs1", "--trending-window", "30"])
        assert ns.trending_window == "30"  # handler will reject


class TestCompareWithPrevArgparse:
    def test_default_false(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.compare_with_prev is False

    def test_set_true(self) -> None:
        ns = build_parser().parse_args(["rs1", "--compare-with-prev"])
        assert ns.compare_with_prev is True


class TestMutexEnforcement:
    def test_trending_with_diff_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--trending-window", "30d", "--diff", "a", "b"])

    def test_trending_with_stats_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--trending-window", "30d", "--stats"])

    def test_compare_with_diff_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--compare-with-prev", "--diff", "a", "b"])


class TestDropFlagRejected:
    """Spec §2.2: --include-drift is dropped (cja-only org-report semantic)."""

    def test_include_drift_unrecognized(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--include-drift"])


class TestSnapshotDirArgparse:
    def test_default_none(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.snapshot_dir is None

    def test_accepts_path(self, tmp_path: Path) -> None:
        ns = build_parser().parse_args(["rs1", "--snapshot-dir", str(tmp_path)])
        assert ns.snapshot_dir == tmp_path

    def test_composes_with_trending_window(self, tmp_path: Path) -> None:
        """--snapshot-dir is non-mutex; composes with --trending-window."""
        ns = build_parser().parse_args(
            ["rs1", "--trending-window", "30d", "--snapshot-dir", str(tmp_path)],
        )
        assert ns.snapshot_dir == tmp_path
        assert ns.trending_window == "30d"


class TestTrendingDispatchEndToEnd:
    """End-to-end: --trending-window reaches cli.commands.trending::run with the right args."""

    def test_dispatch_reaches_handler(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import trending as trending_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(trending_cmd, "run", side_effect=_capture) as mock_run:
            main(["rs1", "--trending-window", "30d", "--snapshot-dir", str(tmp_path)])

        assert mock_run.called
        assert captured["rsids"] == ["rs1"]
        assert captured["duration"] == "30d"
        assert captured["snapshot_dir"] == tmp_path

    def test_dispatch_handles_invalid_duration(self, tmp_path: Path) -> None:
        """Handler must reject bare-int 'duration' with USAGE (2)."""
        from aa_auto_sdr.__main__ import main

        rc = main(["rs1", "--trending-window", "30", "--snapshot-dir", str(tmp_path)])
        assert rc == 2  # ExitCode.USAGE

    def test_dispatch_no_positional_returns_usage(self, tmp_path: Path) -> None:
        from aa_auto_sdr.__main__ import main

        rc = main(["--trending-window", "30d", "--snapshot-dir", str(tmp_path)])
        assert rc == 2  # ExitCode.USAGE
