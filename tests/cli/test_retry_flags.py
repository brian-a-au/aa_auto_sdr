"""Tests for --max-retries / --retry-base-delay / --retry-max-delay."""

from __future__ import annotations

import pytest

from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.core.exit_codes import ExitCode


class TestRetryFlagParsing:
    def test_defaults_are_none_at_parser_level(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(["--list-reportsuites"])
        assert ns.max_retries is None
        assert ns.retry_base_delay is None
        assert ns.retry_max_delay is None

    def test_explicit_values_parse(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(
            ["--list-reportsuites", "--max-retries", "6", "--retry-base-delay", "1.0", "--retry-max-delay", "30.0"]
        )
        assert ns.max_retries == 6
        assert ns.retry_base_delay == 1.0
        assert ns.retry_max_delay == 30.0

    @pytest.mark.parametrize(
        "argv_extra",
        [
            ["--max-retries", "-1"],
            ["--retry-base-delay", "0"],
            ["--retry-base-delay", "-0.5"],
            ["--retry-max-delay", "0"],
        ],
    )
    def test_invalid_values_exit_2(self, argv_extra: list[str]) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--list-reportsuites", *argv_extra])
        assert exc.value.code == 2


class TestRetryFlagMutex:
    """Cross-flag mutex (max < base) is enforced inside cli/main.run before any work."""

    def test_max_less_than_base_exits_usage(self) -> None:
        from aa_auto_sdr.cli.main import run

        rc = run(
            [
                "--list-reportsuites",
                "--retry-base-delay",
                "5.0",
                "--retry-max-delay",
                "1.0",
            ]
        )
        assert rc == ExitCode.USAGE.value
