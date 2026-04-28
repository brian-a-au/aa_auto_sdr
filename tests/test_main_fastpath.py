"""Fast-path entry tests — must complete without importing pandas/aanalytics2."""

import subprocess
import sys


def test_version_flag_short() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1.2.3" in result.stdout


def test_version_flag_long() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1.2.3" in result.stdout


def test_help_flag_does_not_import_aanalytics2() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "aanalytics2" not in result.stderr
    assert "pandas" not in result.stderr


def test_exit_codes_does_not_import_aanalytics2() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "aa_auto_sdr", "--exit-codes"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "aanalytics2" not in result.stderr
    assert "pandas" not in result.stderr


def test_explain_exit_code_does_not_import_aanalytics2() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "aa_auto_sdr", "--explain-exit-code", "11"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "aanalytics2" not in result.stderr
    assert "pandas" not in result.stderr


def test_exit_codes_outputs_full_table() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--exit-codes"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Code" in result.stdout
    for code in (0, 10, 11, 12, 13, 14, 15, 16):
        assert str(code) in result.stdout


def test_completion_does_not_import_aanalytics2() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "aa_auto_sdr", "--completion", "bash"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "aanalytics2" not in result.stderr
    assert "pandas" not in result.stderr


def test_completion_bash_outputs_script() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--completion", "bash"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "complete -F" in result.stdout
