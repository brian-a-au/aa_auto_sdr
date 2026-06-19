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


class TestTrendingHandlerExitCodes:
    """Spec §10 success criterion #3 + §3.10 mode-scoping: empty-window
    returns NOT_FOUND for all-empty, PARTIAL_SUCCESS for some-empty.

    Tested at the handler level (not just compute_trending) because the
    branching at trending.py:121-134 is the actual exit-code decision."""

    def test_all_rsids_empty_returns_not_found(self, tmp_path: Path) -> None:
        from aa_auto_sdr.__main__ import main

        # tmp_path has no snapshots for any RSID — both rsids will be empty.
        rc = main(
            [
                "rs_no_snapshots_a",
                "rs_no_snapshots_b",
                "--trending-window",
                "30d",
                "--snapshot-dir",
                str(tmp_path),
            ]
        )
        assert rc == 13  # ExitCode.NOT_FOUND

    def test_some_rsids_empty_returns_partial_success(self, tmp_path: Path) -> None:
        """One RSID has snapshots; another doesn't → PARTIAL_SUCCESS (14)."""
        import json as _json
        from datetime import UTC, datetime, timedelta

        # Seed a single snapshot for rs_with_data. Timestamp is relative to now
        # so it always lands inside the rolling --trending-window; a hardcoded
        # date eventually falls out of the window and flips the exit code to 13.
        rs_dir = tmp_path / "rs_with_data"
        rs_dir.mkdir()
        ts = datetime.now(UTC) - timedelta(days=1)
        stem = ts.isoformat().replace(":", "-")
        envelope = {
            "schema": "aa-sdr-snapshot/v4",
            "rsid": "rs_with_data",
            "captured_at": ts.isoformat(),
            "tool_version": "1.13.0",
            "degraded_components": [],
            "partial_components": {},
            "quality": None,
            "components": {
                "report_suite": {"rsid": "rs_with_data", "name": "RS_WITH_DATA"},
                "dimensions": [],
                "metrics": [],
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
            },
        }
        (rs_dir / f"{stem}.json").write_text(_json.dumps(envelope))

        from aa_auto_sdr.__main__ import main

        rc = main(
            [
                "rs_with_data",
                "rs_missing",
                "--trending-window",
                "30d",
                "--snapshot-dir",
                str(tmp_path),
            ]
        )
        assert rc == 14  # ExitCode.PARTIAL_SUCCESS


class TestTrendingHandlerSnapshotDirFallthrough:
    """Spec §10 success criterion #16 + §3.9: snapshot dir resolves
    --snapshot-dir flag → --profile → CONFIG (10) error if neither."""

    def test_no_snapshot_dir_no_profile_returns_config(self) -> None:
        """No --snapshot-dir, no --profile → ExitCode.CONFIG (10)."""
        from aa_auto_sdr.__main__ import main

        rc = main(["rs1", "--trending-window", "30d"])
        assert rc == 10  # ExitCode.CONFIG


class TestCompareWithPrevDispatch:
    """Regression: --compare-with-prev dispatch wiring must read the
    correct namespace attribute names (diff_labels, reverse_diff,
    quiet_diff) and CSV-split ignore_fields / show_only — not pass
    them through as raw strings."""

    def test_dispatch_reads_diff_labels_attribute(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Pre-fix the dispatch read ns.labels (which doesn't exist) via
        getattr(ns, "labels", None) — silently dropped --diff-labels.
        Verify dispatch correctly threads --diff-labels through to the
        diff command."""
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            main(
                [
                    "rs1",
                    "--compare-with-prev",
                    "--diff-labels",
                    "A=baseline",
                    "B=candidate",
                ]
            )

        # Pre-fix: labels was None (silent drop). Post-fix: ("baseline", "candidate").
        assert captured["labels"] == ("baseline", "candidate")

    def test_dispatch_reads_reverse_diff_attribute(self) -> None:
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            main(["rs1", "--compare-with-prev", "--reverse-diff"])

        # Pre-fix: reverse=False (silent drop). Post-fix: True.
        assert captured["reverse"] is True

    def test_dispatch_csv_splits_ignore_fields(self) -> None:
        """Pre-fix: frozenset(ns.ignore_fields) → frozenset of CHARS like
        {'d', 'e', 's', 'c', 'r', ...}. Post-fix: split on ','."""
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            main(
                [
                    "rs1",
                    "--compare-with-prev",
                    "--ignore-fields",
                    "description,tags,owner_id",
                ]
            )

        assert captured["ignore_fields"] == frozenset({"description", "tags", "owner_id"})

    def test_dispatch_csv_splits_show_only(self) -> None:
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            main(
                [
                    "rs1",
                    "--compare-with-prev",
                    "--show-only",
                    "metrics,dimensions",
                ]
            )

        assert captured["show_only"] == frozenset({"metrics", "dimensions"})

    def test_dispatch_reads_quiet_diff_not_quiet(self) -> None:
        """`--quiet-diff` is the renderer-level flag; `--quiet` is the
        logger-level flag. Pre-fix used getattr(ns, 'quiet'); post-fix
        uses ns.quiet_diff explicitly."""
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            main(["rs1", "--compare-with-prev", "--quiet-diff"])

        assert captured["quiet"] is True


class TestTrendingDispatchIgnoreFields:
    """Regression: --trending-window dispatch must CSV-split ignore_fields."""

    def test_dispatch_csv_splits_ignore_fields(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import trending as trending_cmd

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(trending_cmd, "run", side_effect=_capture):
            main(
                [
                    "rs1",
                    "--trending-window",
                    "30d",
                    "--snapshot-dir",
                    str(tmp_path),
                    "--ignore-fields",
                    "description,tags",
                ]
            )

        assert captured["ignore_fields"] == ("description", "tags")
