"""End-to-end smoke: invoke the CLI as a subprocess against fully mocked SDK."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_module_invocation_without_args_exits_2(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 2


def test_module_invocation_show_config_with_creds(tmp_path: Path) -> None:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "ORG_ID": "O",
        "CLIENT_ID": "C",
        "SECRET": "S",
        "SCOPES": "X",
    }
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--show-config"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 0
    assert "env" in result.stdout


def test_version_invocation(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "1.1.0" in result.stdout
