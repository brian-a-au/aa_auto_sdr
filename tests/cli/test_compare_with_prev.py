"""--compare-with-prev — sugar over `--diff <RSID>@previous <RSID>@latest`."""

from __future__ import annotations

from unittest.mock import patch

from aa_auto_sdr.cli.commands import compare_with_prev as cmd
from aa_auto_sdr.cli.commands import diff as diff_cmd
from aa_auto_sdr.core.exit_codes import ExitCode


class TestSingleRsidDispatch:
    def test_synthesizes_at_previous_at_latest_pair(self) -> None:
        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            cmd.run(
                rsids=["rs1"],
                profile=None,
                format_name=None,
                output=None,
                side_by_side=False,
                summary=False,
                ignore_fields=frozenset(),
                extended_fields=False,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert captured["a"] == "rs1@previous"
        assert captured["b"] == "rs1@latest"


class TestPassThrough:
    def test_format_and_side_by_side_pass_through(self) -> None:
        captured: dict = {}

        def _stub(**kw: object) -> int:
            captured.update(kw)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_stub):
            cmd.run(
                rsids=["rs1"],
                profile="prod",
                format_name="markdown",
                output="-",
                side_by_side=True,
                summary=False,
                ignore_fields=frozenset({"description"}),
                extended_fields=True,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert captured["format_name"] == "markdown"
        assert captured["side_by_side"] is True
        assert captured["extended_fields"] is True
        assert captured["ignore_fields"] == frozenset({"description"})
        assert captured["profile"] == "prod"


class TestMultiRsid:
    def test_runs_diff_once_per_rsid_returns_worst_exit(self) -> None:
        # First RSID succeeds (0), second errors (NOT_FOUND, 13).
        side_effects = iter([ExitCode.OK.value, ExitCode.NOT_FOUND.value])

        def _stub(**kwargs: object) -> int:
            return next(side_effects)

        with patch.object(diff_cmd, "run", side_effect=_stub) as mock_run:
            rc = cmd.run(
                rsids=["rs1", "rs2"],
                profile=None,
                format_name=None,
                output=None,
                side_by_side=False,
                summary=False,
                ignore_fields=frozenset(),
                extended_fields=False,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert mock_run.call_count == 2
        # Worst exit (NOT_FOUND) wins.
        assert rc == ExitCode.NOT_FOUND.value


class TestNoPositional:
    def test_empty_rsids_returns_usage(self) -> None:
        rc = cmd.run(
            rsids=[],
            profile=None,
            format_name=None,
            output=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            extended_fields=False,
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
            color_theme="default",
        )
        assert rc == ExitCode.USAGE.value


class TestSnapshotDirThreading:
    def test_snapshot_dir_is_forwarded_to_diff_run(self) -> None:
        """compare_with_prev threads snapshot_dir through to diff_cmd.run."""
        from pathlib import Path

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        explicit = Path("/tmp/explicit_snaps")
        with patch.object(diff_cmd, "run", side_effect=_capture):
            cmd.run(
                rsids=["rs1"],
                profile=None,
                snapshot_dir=explicit,
                format_name=None,
                output=None,
                side_by_side=False,
                summary=False,
                ignore_fields=frozenset(),
                extended_fields=False,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert captured["snapshot_dir"] == explicit
