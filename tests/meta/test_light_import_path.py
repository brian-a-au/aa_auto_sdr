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
