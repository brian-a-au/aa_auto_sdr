"""--quiet: console handler at WARNING; file handler stays at numeric --log-level."""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from aa_auto_sdr.core.logging import setup_logging


@pytest.fixture(autouse=True)
def _reset_root_logger():
    saved = logging.root.handlers[:]
    saved_lvl = logging.root.level
    yield
    for h in logging.root.handlers[:]:
        h.close()
        logging.root.removeHandler(h)
    for h in saved:
        logging.root.addHandler(h)
    logging.root.setLevel(saved_lvl)


def _ns(**kw):
    base = {
        "log_level": None,
        "log_format": "text",
        "quiet": False,
        "rsids": ["abc"],
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
    base.update(kw)
    return argparse.Namespace(**base)


def _handlers_by_kind() -> dict[str, logging.Handler]:
    out: dict[str, logging.Handler] = {}
    for h in logging.root.handlers:
        if isinstance(h, RotatingFileHandler):
            out["file"] = h
        elif isinstance(h, logging.StreamHandler):
            out["console"] = h
    return out


def test_quiet_routes_to_warning_on_console(tmp_path: Path) -> None:
    setup_logging(_ns(quiet=True), log_dir=tmp_path / "logs")
    h = _handlers_by_kind()
    assert h["console"].level == logging.WARNING


def test_quiet_does_not_mute_file(tmp_path: Path) -> None:
    setup_logging(_ns(quiet=True, log_level="INFO"), log_dir=tmp_path / "logs")
    h = _handlers_by_kind()
    assert h["file"].level == logging.INFO


def test_quiet_with_debug_level_file_at_debug(tmp_path: Path) -> None:
    setup_logging(_ns(quiet=True, log_level="DEBUG"), log_dir=tmp_path / "logs")
    h = _handlers_by_kind()
    assert h["file"].level == logging.DEBUG
    assert h["console"].level == logging.WARNING


def test_no_quiet_console_at_numeric_level(tmp_path: Path) -> None:
    setup_logging(_ns(quiet=False, log_level="DEBUG"), log_dir=tmp_path / "logs")
    h = _handlers_by_kind()
    assert h["console"].level == logging.DEBUG
    assert h["file"].level == logging.DEBUG


def test_quiet_info_record_appears_in_file_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_ns(quiet=True, log_level="INFO"), log_dir=tmp_path / "logs")
    capsys.readouterr()  # discard startup-banner stderr
    logging.getLogger("aa_auto_sdr.test").info("only-in-file marker 12345")
    for h in logging.root.handlers:
        h.flush()
    err = capsys.readouterr().err
    assert "only-in-file marker 12345" not in err
    log_file = next((tmp_path / "logs").glob("*.log"))
    assert "only-in-file marker 12345" in log_file.read_text()


def test_warning_appears_on_console_under_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(_ns(quiet=True, log_level="INFO"), log_dir=tmp_path / "logs")
    capsys.readouterr()  # discard startup-banner stderr
    logging.getLogger("aa_auto_sdr.test").warning("show-this 99")
    err = capsys.readouterr().err
    assert "show-this 99" in err
