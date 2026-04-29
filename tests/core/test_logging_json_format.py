"""JSONFormatter: NDJSON output, schema enforcement, reserved-field exclusion."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pytest

from aa_auto_sdr.core.logging import RUN_ID, setup_logging


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


def _ns(log_format="json", **kw):
    base = {
        "log_level": None,
        "log_format": log_format,
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


def test_json_record_is_valid_ndjson(tmp_path: Path) -> None:
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    logging.getLogger("aa_auto_sdr.test").info("hello")
    log_file = next((tmp_path / "logs").glob("*.log"))
    text = log_file.read_text(encoding="utf-8")
    for line in text.strip().splitlines():
        json.loads(line)  # raises if not valid JSON


def test_json_required_keys_present(tmp_path: Path) -> None:
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    logging.getLogger("aa_auto_sdr.test").info("hello")
    log_file = next((tmp_path / "logs").glob("*.log"))
    last = json.loads(log_file.read_text().strip().splitlines()[-1])
    for key in ("timestamp", "level", "logger", "message", "run_id", "run_mode", "tool_version"):
        assert key in last, f"missing required key: {key}"
    assert last["run_id"] == RUN_ID
    assert last["run_mode"] == "single"


def test_json_extra_fields_plumbed(tmp_path: Path) -> None:
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    logging.getLogger("aa_auto_sdr.test").info("with extra", extra={"rsid": "xyz", "duration_ms": 42})
    log_file = next((tmp_path / "logs").glob("*.log"))
    last = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert last["rsid"] == "xyz"
    assert last["duration_ms"] == 42


def test_json_excludes_reserved_logrecord_fields(tmp_path: Path) -> None:
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    logging.getLogger("aa_auto_sdr.test").info("hello")
    log_file = next((tmp_path / "logs").glob("*.log"))
    last = json.loads(log_file.read_text().strip().splitlines()[-1])
    for forbidden in ("pathname", "filename", "module", "lineno", "funcName", "exc_text", "stack_info"):
        assert forbidden not in last, f"reserved LogRecord field leaked: {forbidden}"


def test_json_redacted_extra_field(tmp_path: Path) -> None:
    setup_logging(_ns(), log_dir=tmp_path / "logs")
    logging.getLogger("aa_auto_sdr.test").info("login", extra={"client_secret": "leaky"})
    log_file = next((tmp_path / "logs").glob("*.log"))
    last = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert last["client_secret"] == "[REDACTED]"
    assert "leaky" not in json.dumps(last)


def test_text_format_remains_default(tmp_path: Path) -> None:
    """When --log-format is not 'json', file content is plain text — not JSON."""
    setup_logging(_ns(log_format="text"), log_dir=tmp_path / "logs")
    logging.getLogger("aa_auto_sdr.test").info("hello plain")
    log_file = next((tmp_path / "logs").glob("*.log"))
    line = log_file.read_text().strip().splitlines()[-1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)
    assert "hello plain" in line
