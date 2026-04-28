"""setup_logging: handler wiring, level resolution, idempotent re-init.

Each test uses pytest's tmp_path fixture so log files do not pollute the
repo's logs/ directory. Each test resets the root logger after running."""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from aa_auto_sdr.core.logging import VALID_LEVELS, _log_filename, setup_logging


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
    """Namespace covering every field setup_logging or infer_run_mode reads."""
    base = {
        "log_level": None,
        "log_format": "text",
        "quiet": False,
        "rsids": [],
        "batch": [],
        "diff": None,
        "list_reportsuites": False,
        "list_virtual_reportsuites": False,
        "describe_reportsuite": None,
        "list_metrics": None,
        "list_dimensions": None,
        "list_segments": None,
        "list_calculated_metrics": None,
        "list_classification_datasets": None,
        "list_snapshots": False,
        "prune_snapshots": False,
        "profile_add": None,
        "profile_test": None,
        "profile_show": None,
        "profile_list": False,
        "profile_import": None,
        "show_config": False,
        "config_status": False,
        "validate_config": False,
        "sample_config": False,
        "stats": False,
        "interactive": False,
    }
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
    assert n1 == n2


def test_valid_levels_constant() -> None:
    assert VALID_LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def test_filename_for_single_uses_rsid() -> None:
    name = _log_filename("single", _ns(rsids=["xyz123"]), "20260428_120000")
    assert name == "SDR_Generation_xyz123_20260428_120000.log"


def test_filename_for_batch() -> None:
    name = _log_filename("batch", _ns(rsids=["A", "B"]), "20260428_120000")
    assert name == "SDR_Batch_Generation_20260428_120000.log"


def test_filename_for_diff() -> None:
    name = _log_filename("diff", _ns(diff=["a", "b"]), "20260428_120000")
    assert name == "SDR_Diff_20260428_120000.log"


@pytest.mark.parametrize(
    "mode", ["discovery", "inspect", "snapshot", "profile", "config", "stats", "interactive", "other"]
)
def test_filename_catchall(mode: str) -> None:
    name = _log_filename(mode, _ns(), "20260428_120000")
    assert name == "SDR_Run_20260428_120000.log"


def test_filename_single_without_rsid_falls_through_to_catchall() -> None:
    """Defensive: 'single' is only produced by infer_run_mode when rsids is non-empty,
    but _log_filename guards against being called with empty rsids — falls through
    to the catch-all 'SDR_Run_...' shape rather than raising IndexError."""
    name = _log_filename("single", _ns(), "20260428_120000")
    assert name == "SDR_Run_20260428_120000.log"


def test_setup_logging_creates_log_file(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    setup_logging(_ns(rsids=["abc"]), log_dir=log_dir)
    log_files = list(log_dir.glob("SDR_Generation_abc_*.log"))
    assert len(log_files) == 1


def test_file_handler_is_rotating(tmp_path: Path) -> None:
    setup_logging(_ns(rsids=["abc"]), log_dir=tmp_path / "logs")
    rotating = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) == 1


def test_mkdir_permission_error_falls_back_to_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _raise(self, *_a, **_kw):
        raise PermissionError("read-only volume")

    monkeypatch.setattr(Path, "mkdir", _raise)
    setup_logging(_ns(rsids=["abc"]), log_dir=tmp_path / "logs")
    rotating = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
    assert rotating == []
    err = capsys.readouterr().err
    assert "Cannot create logs directory" in err


def test_mkdir_oserror_falls_back_to_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """OSError (e.g., disk full, ENOSPC) is also tolerated — same fallback path
    as PermissionError. Documents the broader except clause."""

    def _raise(self, *_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", _raise)
    setup_logging(_ns(rsids=["abc"]), log_dir=tmp_path / "logs")
    rotating = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
    assert rotating == []
    err = capsys.readouterr().err
    assert "Cannot create logs directory" in err


def test_idempotent_reinit_with_file_handler(tmp_path: Path) -> None:
    """Re-init should close & remove the old file handler before adding a new one
    so the file count stays at 1, not 2."""
    setup_logging(_ns(rsids=["abc"]), log_dir=tmp_path / "logs")
    setup_logging(_ns(rsids=["abc"]), log_dir=tmp_path / "logs")
    rotating = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) == 1
