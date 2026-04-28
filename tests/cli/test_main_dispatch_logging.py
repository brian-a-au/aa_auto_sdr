"""cli.main.run() must call setup_logging exactly once. The fast-path
entries in __main__ must NOT call setup_logging at all."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

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


def test_sample_config_writes_log_file_with_banner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: cli.main.run() through real (un-mocked) setup_logging writes
    a per-run log file under ./logs/ containing the five-record banner.

    Catches future regressions where setup_logging is wired but the file
    handler stops actually receiving records (e.g., after a refactor of the
    handler-attach order or banner-emit timing)."""
    from aa_auto_sdr.cli import main as cli_main

    saved_handlers = logging.root.handlers[:]
    saved_level = logging.root.level
    monkeypatch.chdir(tmp_path)
    try:
        rc = cli_main.run(["--sample-config"])
        assert rc == 0
        for h in logging.root.handlers:
            h.flush()
        log_dir = tmp_path / "logs"
        assert log_dir.exists(), "logs/ should be created relative to cwd"
        log_files = list(log_dir.glob("SDR_Run_*.log"))
        assert len(log_files) == 1, f"expected one SDR_Run_*.log file, got {log_files}"
        text = log_files[0].read_text(encoding="utf-8")
        assert "Logging initialized. Log file:" in text
        assert "aa_auto_sdr version:" in text
        assert "Dependencies:" in text
        assert "Run mode: config" in text
    finally:
        for h in logging.root.handlers[:]:
            h.close()
            logging.root.removeHandler(h)
        for h in saved_handlers:
            logging.root.addHandler(h)
        logging.root.setLevel(saved_level)
