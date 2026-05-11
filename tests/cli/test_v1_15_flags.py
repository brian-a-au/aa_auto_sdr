"""v1.15.0 CLI flag surface: --git-commit, --git-push, --git-message.

Also: dropped flags `--git-init` and `--git-push-on-change` are argparse-rejected.
"""

from __future__ import annotations

import argparse

import pytest

from aa_auto_sdr.cli.parser import build_parser


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
            trending_window=None,
            compare_with_prev=False,
            inventory_summary=False,
        )
        rc = _validate_git_modifiers(ns)
        assert rc == int(ExitCode.OK)


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
