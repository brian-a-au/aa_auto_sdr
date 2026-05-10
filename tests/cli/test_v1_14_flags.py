"""v1.14.0 CLI flag surface: --watch, --interval, --watch-threshold.

Also: dropped flag `--on-change` is argparse-rejected.
"""

from __future__ import annotations

import argparse

import pytest

from aa_auto_sdr.cli.parser import build_parser


@pytest.fixture
def parser():
    return build_parser()


class TestWatchAndInterval:
    def test_watch_with_interval_parses(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--watch", "--interval", "1h"])
        assert ns.watch is True
        assert ns.interval == "1h"
        assert ns.rsids == ["rs_a"]

    def test_watch_with_multiple_rsids(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "rs_b", "--watch", "--interval", "30d"])
        assert ns.rsids == ["rs_a", "rs_b"]

    def test_watch_threshold_int(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--watch", "--interval", "1h", "--watch-threshold", "5"])
        assert ns.watch_threshold == 5

    def test_watch_threshold_default_is_one(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--watch", "--interval", "1h"])
        assert ns.watch_threshold == 1

    def test_watch_threshold_zero_allowed(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--watch", "--interval", "1h", "--watch-threshold", "0"])
        assert ns.watch_threshold == 0

    def test_watch_without_interval_is_argparse_ok_but_handler_rejects(self, parser) -> None:
        ns = parser.parse_args(["rs_a", "--watch"])
        assert ns.watch is True
        assert ns.interval is None


class TestDroppedOnChangeFlag:
    def test_on_change_is_argparse_rejected(self, parser, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["rs_a", "--on-change", "echo hi"])
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "unrecognized" in captured.err.lower()


class TestMutexWithOtherActions:
    @pytest.mark.parametrize(
        "other",
        [
            ["--diff", "rs_a@previous", "rs_a@latest"],
            ["--stats"],
            ["--list-reportsuites"],
            ["--list-virtual-reportsuites"],
            ["--trending-window", "30d"],
            ["--compare-with-prev"],
            ["--inventory-summary"],
        ],
    )
    def test_watch_plus_other_action_rejected(self, parser, other) -> None:
        with pytest.raises(SystemExit):
            parser.parse_args(["rs_a", "--watch", "--interval", "1h", *other])


class TestPreDispatchValidator:
    """`--interval` and non-default `--watch-threshold` without `--watch` are
    rejected by a pre-dispatch validator in cli/main.py."""

    def test_interval_without_watch_returns_usage(self, capsys) -> None:
        from aa_auto_sdr.cli.main import _validate_watch_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(watch=False, interval="1h", watch_threshold=1)
        rc = _validate_watch_modifiers(ns)
        assert rc == int(ExitCode.USAGE)
        err = capsys.readouterr().err
        assert "--interval" in err
        assert "--watch" in err

    def test_watch_threshold_without_watch_returns_usage(self, capsys) -> None:
        from aa_auto_sdr.cli.main import _validate_watch_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(watch=False, interval=None, watch_threshold=5)
        rc = _validate_watch_modifiers(ns)
        assert rc == int(ExitCode.USAGE)
        err = capsys.readouterr().err
        assert "--watch-threshold" in err

    def test_default_threshold_without_watch_is_fine(self) -> None:
        from aa_auto_sdr.cli.main import _validate_watch_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(watch=False, interval=None, watch_threshold=1)
        rc = _validate_watch_modifiers(ns)
        assert rc == int(ExitCode.OK)

    def test_watch_with_modifiers_is_fine(self) -> None:
        from aa_auto_sdr.cli.main import _validate_watch_modifiers
        from aa_auto_sdr.core.exit_codes import ExitCode

        ns = argparse.Namespace(watch=True, interval="1h", watch_threshold=5)
        rc = _validate_watch_modifiers(ns)
        assert rc == int(ExitCode.OK)


class TestHelpListsNewFlags:
    def test_help_mentions_watch(self, capsys) -> None:
        from aa_auto_sdr.__main__ import _print_help

        _print_help()
        out = capsys.readouterr().out
        assert "--watch" in out
        assert "--interval" in out
        assert "--watch-threshold" in out

    def test_help_does_not_mention_on_change(self, capsys) -> None:
        from aa_auto_sdr.__main__ import _print_help

        _print_help()
        out = capsys.readouterr().out
        assert "--on-change" not in out
