"""infer_run_mode maps a parsed argparse Namespace to one of the eleven
documented run-mode strings. Test one branch per mode."""

from __future__ import annotations

import argparse
from typing import Any

import pytest

from aa_auto_sdr.core.logging import infer_run_mode


def _ns(**overrides: Any) -> argparse.Namespace:
    """Build a Namespace whose fields are all falsy unless explicitly overridden."""
    base = {
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
    base.update(overrides)
    return argparse.Namespace(**base)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"diff": ["a", "b"]}, "diff"),
        ({"batch": ["RS1", "RS2"]}, "batch"),
        ({"rsids": ["RS1", "RS2"]}, "batch"),
        ({"list_reportsuites": True}, "discovery"),
        ({"list_virtual_reportsuites": True}, "discovery"),
        ({"describe_reportsuite": "RS1"}, "inspect"),
        ({"list_metrics": "RS1"}, "inspect"),
        ({"list_dimensions": "RS1"}, "inspect"),
        ({"list_segments": "RS1"}, "inspect"),
        ({"list_calculated_metrics": "RS1"}, "inspect"),
        ({"list_classification_datasets": "RS1"}, "inspect"),
        ({"list_snapshots": True}, "snapshot"),
        ({"prune_snapshots": True}, "snapshot"),
        ({"profile_add": "name"}, "profile"),
        ({"profile_test": "name"}, "profile"),
        ({"profile_show": "name"}, "profile"),
        ({"profile_list": True}, "profile"),
        ({"profile_import": ("name", "/tmp/x")}, "profile"),
        ({"show_config": True}, "config"),
        ({"config_status": True}, "config"),
        ({"validate_config": True}, "config"),
        ({"sample_config": True}, "config"),
        ({"stats": True}, "stats"),
        ({"interactive": True}, "interactive"),
        ({"rsids": ["RS1"]}, "single"),
        ({}, "other"),
    ],
)
def test_infer_run_mode(overrides: dict[str, Any], expected: str) -> None:
    assert infer_run_mode(_ns(**overrides)) == expected
