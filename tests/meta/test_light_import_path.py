"""Importing the CLI dispatcher must not drag in the heavy stack."""

from __future__ import annotations

import subprocess
import sys


def test_cli_main_import_stays_light():
    # Fresh interpreter so nothing is pre-imported by the test session.
    code = (
        "import importlib, sys;"
        "importlib.import_module('aa_auto_sdr.cli.main');"
        "heavy = [m for m in ('pandas', 'aanalytics2', 'requests') if m in sys.modules];"
        "print(','.join(heavy));"
        "sys.exit(1 if heavy else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"heavy modules imported: {result.stdout.strip()}"


def test_light_command_runtime_stays_light(tmp_path):
    """The runtime path a light command takes — setup_logging + a log record —
    must not drag in the heavy stack either (WorkerIdFilter regression guard)."""
    code = (
        "import argparse, importlib, logging, sys;"
        "importlib.import_module('aa_auto_sdr.cli.main');"
        "core_logging = importlib.import_module('aa_auto_sdr.core.logging');"
        "core_logging.setup_logging(argparse.Namespace());"
        "logging.getLogger('aa_auto_sdr').info('light-command log record');"
        "heavy = [m for m in ('pandas', 'aanalytics2', 'requests') if m in sys.modules];"
        "print(','.join(heavy));"
        "sys.exit(1 if heavy else 0)"
    )
    # cwd=tmp_path so setup_logging's logs/ dir lands in the temp dir, not the repo.
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, f"heavy modules imported at runtime: {result.stdout.strip()}"
