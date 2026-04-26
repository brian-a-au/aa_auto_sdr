"""Fast-path entry tests — must complete without importing pandas/aanalytics2."""
import subprocess
import sys


def test_version_flag_short() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True, text=True, check=True,
    )
    assert "0.1.0" in result.stdout


def test_version_flag_long() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--version"],
        capture_output=True, text=True, check=True,
    )
    assert "0.1.0" in result.stdout


def test_help_flag_does_not_import_aanalytics2() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "aa_auto_sdr", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "aanalytics2" not in result.stderr
    assert "pandas" not in result.stderr
