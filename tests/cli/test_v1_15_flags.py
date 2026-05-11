"""v1.15.0 CLI flag surface: --git-commit, --git-push, --git-message.

Also: dropped flags `--git-init` and `--git-push-on-change` are argparse-rejected.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.snapshot.git import GitOpResult


@pytest.fixture
def parser():
    return build_parser()


class TestGitFlagsParse:
    def test_git_commit_alone_parses(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--git-commit"])
        assert ns.git_commit is True
        assert ns.git_push is False
        assert ns.git_message is None

    def test_git_commit_push_parse(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--git-commit", "--git-push"])
        assert ns.git_commit is True
        assert ns.git_push is True

    def test_git_message_value(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--git-commit", "--git-message", "release v2.3"])
        assert ns.git_message == "release v2.3"

    def test_default_git_commit_false(self, parser) -> None:
        ns = parser.parse_args(["rs_a"])
        assert ns.git_commit is False
        assert ns.git_push is False
        assert ns.git_message is None


class TestDroppedFlags:
    def test_git_init_argparse_rejected(self, parser, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["rs_a", "--git-init"])
        assert exc.value.code == 2
        assert "unrecognized" in capsys.readouterr().err.lower()

    def test_git_push_on_change_argparse_rejected(self, parser, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["rs_a", "--git-push-on-change"])
        assert exc.value.code == 2
        assert "unrecognized" in capsys.readouterr().err.lower()


class TestPreDispatchValidator:
    def test_git_push_without_git_commit_rejected(self, capsys) -> None:
        from aa_auto_sdr.cli.main import _validate_git_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(
            git_commit=False,
            git_push=True,
            git_message=None,
            diff=None,
            stats=False,
            list_reportsuites=False,
            list_virtual_reportsuites=False,
            describe_reportsuite=False,
            list_metrics=None,
            list_dimensions=None,
            list_segments=None,
            list_calculated_metrics=None,
            list_classification_datasets=None,
            trending_window=None,
            compare_with_prev=False,
            inventory_summary=False,
        )
        rc = _validate_git_modifiers(ns)
        assert rc == int(ExitCode.USAGE)
        err = capsys.readouterr().err
        assert "--git-push" in err
        assert "--git-commit" in err

    def test_git_message_without_git_commit_rejected(self, capsys) -> None:
        from aa_auto_sdr.cli.main import _validate_git_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(
            git_commit=False,
            git_push=False,
            git_message="x",
            diff=None,
            stats=False,
            list_reportsuites=False,
            list_virtual_reportsuites=False,
            describe_reportsuite=False,
            list_metrics=None,
            list_dimensions=None,
            list_segments=None,
            list_calculated_metrics=None,
            list_classification_datasets=None,
            trending_window=None,
            compare_with_prev=False,
            inventory_summary=False,
        )
        rc = _validate_git_modifiers(ns)
        assert rc == int(ExitCode.USAGE)
        err = capsys.readouterr().err
        assert "--git-message" in err

    @pytest.mark.parametrize(
        ("blocking_attr", "blocking_value"),
        [
            ("diff", ["rs_a@previous", "rs_a@latest"]),
            ("stats", True),
            ("list_reportsuites", True),
            ("trending_window", "30d"),
            ("compare_with_prev", True),
            ("inventory_summary", True),
            ("list_classification_datasets", "rs_a"),
        ],
    )
    def test_git_commit_with_non_generating_action_rejected(
        self,
        blocking_attr,
        blocking_value,
        capsys,
    ) -> None:
        from aa_auto_sdr.cli.main import _validate_git_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(
            git_commit=True,
            git_push=False,
            git_message=None,
            diff=None,
            stats=False,
            list_reportsuites=False,
            list_virtual_reportsuites=False,
            describe_reportsuite=False,
            list_metrics=None,
            list_dimensions=None,
            list_segments=None,
            list_calculated_metrics=None,
            list_classification_datasets=None,
            trending_window=None,
            compare_with_prev=False,
            inventory_summary=False,
        )
        setattr(ns, blocking_attr, blocking_value)
        rc = _validate_git_modifiers(ns)
        assert rc == int(ExitCode.USAGE)
        err = capsys.readouterr().err
        assert "--git-commit" in err

    def test_git_commit_with_generating_action_ok(self) -> None:
        from aa_auto_sdr.cli.main import _validate_git_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(
            git_commit=True,
            git_push=False,
            git_message=None,
            diff=None,
            stats=False,
            list_reportsuites=False,
            list_virtual_reportsuites=False,
            describe_reportsuite=False,
            list_metrics=None,
            list_dimensions=None,
            list_segments=None,
            list_calculated_metrics=None,
            list_classification_datasets=None,
            trending_window=None,
            compare_with_prev=False,
            inventory_summary=False,
        )
        rc = _validate_git_modifiers(ns)
        assert rc == int(ExitCode.OK)


class TestGitCommitImpliesAutoSnapshot:
    """--git-commit must imply save_required so snapshot_dir is resolved (C1)."""

    def test_generate_git_commit_without_profile_resolves_to_default(self, capsys, tmp_path: Path) -> None:
        """v1.15.0 P1 fix: --git-commit without --profile falls back to 'default'
        profile dir rather than returning CONFIG (10). The run proceeds past the
        snapshot-dir check to auth/API. save_required is still True (no silent no-op)."""
        from aa_auto_sdr.cli.commands import generate as generate_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline.models import RunResult

        ok_result = RunResult(
            rsid="rs_a",
            success=True,
            outputs=[tmp_path / "rs_a.json"],
            report_suite_name="Test Suite",
            git_op=GitOpResult(ok=True, committed=True, commit_sha="a" * 40),
        )

        captured_snapshot_dirs: list = []

        def fake_run_single(**kwargs):
            captured_snapshot_dirs.append(kwargs.get("snapshot_dir"))
            return ok_result

        from aa_auto_sdr.pipeline import single as single_mod

        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(single_mod, "run_single", side_effect=fake_run_single),
        ):
            rc = generate_cmd._run_impl(
                rsid="rs_a",
                output_dir=tmp_path,
                format_name="json",
                profile=None,  # no profile
                git_commit=True,
                git_push=False,
                git_message=None,
            )
        # Must NOT be CONFIG (10)
        assert rc == ExitCode.OK.value
        # snapshot_dir resolved to default (not None, not errored)
        assert len(captured_snapshot_dirs) == 1
        assert captured_snapshot_dirs[0] is not None
        assert "default" in str(captured_snapshot_dirs[0])

    def test_generate_git_commit_with_profile_calls_git_commit_snapshot(self, tmp_path: Path) -> None:
        """When --git-commit=True and a profile is set, git_commit_snapshot must
        be called — snapshot_dir is not None (the implication is in effect)."""
        from aa_auto_sdr.cli.commands import generate as generate_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.snapshot.git import GitOpResult

        fake_doc = MagicMock()
        fake_doc.quality = None
        fake_doc.report_suite.name = "Test Suite"

        fake_writer = MagicMock()
        fake_writer.extension = ".json"
        fake_writer.write.return_value = [tmp_path / "rs_a.json"]

        git_result = GitOpResult(ok=True, committed=True, commit_sha="a" * 40)

        with (
            patch("aa_auto_sdr.core.credentials.resolve") as mock_creds,
            patch("aa_auto_sdr.api.client.AaClient.from_credentials") as mock_client,
            patch("aa_auto_sdr.pipeline.single.build_sdr", return_value=fake_doc),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=fake_writer),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.snapshot.store.save_snapshot", return_value=tmp_path / "snap.json"),
            patch(
                "aa_auto_sdr.snapshot.git.git_commit_snapshot",
                return_value=git_result,
            ) as mock_git,
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
        ):
            mock_creds.return_value = MagicMock()
            mock_client.return_value = MagicMock()
            rc = generate_cmd._run_impl(
                rsid="rs_a",
                output_dir=tmp_path,
                format_name="json",
                profile="testprofile",
                git_commit=True,
                git_push=False,
                git_message=None,
            )

        assert rc == ExitCode.OK.value
        mock_git.assert_called_once()

    def test_batch_git_commit_without_profile_resolves_to_default(self, capsys, tmp_path: Path) -> None:
        """v1.15.0 P1 fix: batch --git-commit without --profile falls back to
        'default' profile dir. No longer returns CONFIG (10) at the profile check."""
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline import batch as batch_mod
        from aa_auto_sdr.pipeline.models import BatchResult, RunResult

        ok_result = RunResult(
            rsid="rs_a",
            success=True,
            outputs=[],
            report_suite_name="Test Suite",
            git_op=GitOpResult(ok=True, committed=True, commit_sha="b" * 40),
        )
        batch_result = BatchResult(
            successes=[ok_result],
            failures=[],
            total_duration_seconds=0.1,
            total_output_bytes=0,
        )

        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(batch_mod, "run_batch", return_value=batch_result),
        ):
            rc = batch_cmd._run_impl(
                rsids=["rs_a"],
                output_dir=tmp_path,
                format_name="json",
                profile=None,  # no profile
                git_commit=True,
                git_push=False,
                git_message=None,
            )
        # Must NOT be CONFIG (10)
        assert rc == ExitCode.OK.value


class TestHelpListsFlags:
    def test_help_mentions_git_flags(self, capsys) -> None:
        from aa_auto_sdr.__main__ import _print_help

        _print_help()
        out = capsys.readouterr().out
        assert "--git-commit" in out
        assert "--git-push" in out
        assert "--git-message" in out

    def test_help_does_not_mention_dropped(self, capsys) -> None:
        from aa_auto_sdr.__main__ import _print_help

        _print_help()
        out = capsys.readouterr().out
        assert "--git-init" not in out
        assert "--git-push-on-change" not in out
