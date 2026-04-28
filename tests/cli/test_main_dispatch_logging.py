"""cli.main.run() must call setup_logging exactly once. The fast-path
entries in __main__ must NOT call setup_logging at all."""

from __future__ import annotations

from unittest.mock import patch

from aa_auto_sdr import __main__ as fastpath


def test_main_run_calls_setup_logging_once() -> None:
    from aa_auto_sdr.cli import main as cli_main

    with patch.object(cli_main, "setup_logging") as mock_setup:
        # --sample-config is config-only — no auth, no network.
        cli_main.run(["--sample-config"])
    assert mock_setup.call_count == 1


def test_fastpath_version_does_not_init_logging() -> None:
    with patch("aa_auto_sdr.cli.main.setup_logging") as mock_setup:
        rc = fastpath.main(["--version"])
    assert rc == 0
    assert mock_setup.call_count == 0


def test_fastpath_help_does_not_init_logging() -> None:
    with patch("aa_auto_sdr.cli.main.setup_logging") as mock_setup:
        rc = fastpath.main(["--help"])
    assert rc == 0
    assert mock_setup.call_count == 0


def test_fastpath_exit_codes_does_not_init_logging() -> None:
    with patch("aa_auto_sdr.cli.main.setup_logging") as mock_setup:
        rc = fastpath.main(["--exit-codes"])
    assert rc == 0
    assert mock_setup.call_count == 0
