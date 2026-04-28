"""setup_logging: handler wiring, level resolution, idempotent re-init.

Each test uses pytest's tmp_path fixture so log files do not pollute the
repo's logs/ directory. Each test resets the root logger after running."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pytest

from aa_auto_sdr.core.logging import VALID_LEVELS, setup_logging


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Each test starts with a clean root logger and restores it on exit."""
    saved_handlers = logging.root.handlers[:]
    saved_level = logging.root.level
    yield
    for h in logging.root.handlers[:]:
        h.close()
        logging.root.removeHandler(h)
    for h in saved_handlers:
        logging.root.addHandler(h)
    logging.root.setLevel(saved_level)


def _ns(**kwargs):
    base = {"log_level": None, "log_format": "text", "quiet": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_setup_logging_returns_aa_auto_sdr_logger(tmp_path: Path) -> None:
    logger = setup_logging(_ns(), log_dir=tmp_path / "logs")
    assert logger.name == "aa_auto_sdr"


def test_default_level_is_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    assert logging.root.level == logging.INFO


def test_log_level_flag_overrides_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    setup_logging(_ns(log_level="DEBUG"), log_dir=tmp_path / "logs")
    assert logging.root.level == logging.DEBUG


def test_env_var_used_when_flag_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    assert logging.root.level == logging.ERROR


def test_invalid_level_falls_back_to_info(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_ns(log_level="LOUD"), log_dir=tmp_path / "logs")
    assert logging.root.level == logging.INFO
    err = capsys.readouterr().err
    assert "Warning: invalid log level 'LOUD'" in err


def test_idempotent_reinit_replaces_handlers(tmp_path: Path) -> None:
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    n1 = len(logging.root.handlers)
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    n2 = len(logging.root.handlers)
    assert n1 == n2  # Task 2 skeleton: console only, so n1 == n2 == 1


def test_valid_levels_constant() -> None:
    assert VALID_LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
