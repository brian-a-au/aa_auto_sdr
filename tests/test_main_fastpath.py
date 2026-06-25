"""Fast-path entry tests — must complete without importing pandas/aanalytics2."""

import subprocess
import sys

from aa_auto_sdr.__main__ import main


def test_version_flag_short() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1.21.2" in result.stdout


def test_version_flag_long() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "1.21.2" in result.stdout


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


def test_help_lists_sampling_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--sample " in out or "--sample N" in out
    assert "--sample-seed" in out
    assert "--sample-stratified" in out
    assert "--memory-limit" not in out
    assert "--memory-warning" not in out


def test_help_lists_inventory_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--inventory-summary" in out
    assert "--inventory-only" not in out


def test_help_lists_quality_engine_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--quality-report" in out
    assert "--quality-policy" in out
    assert "--fail-on-quality" in out


def test_help_lists_trending_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--trending-window" in out
    assert "--compare-with-prev" in out
    assert "--include-drift" not in out


def test_help_lists_watch_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--watch" in out
    assert "--interval" in out
    assert "--watch-threshold" in out
    assert "--on-change" not in out


def test_help_lists_git_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--git-commit" in out
    assert "--git-push" in out
    assert "--git-message" in out
    assert "--git-init" not in out
    assert "--git-push-on-change" not in out


def test_explain_exit_code_without_arg_returns_usage(capsys) -> None:
    """`--explain-exit-code` with no CODE → usage error, exit 2."""
    rc = main(["--explain-exit-code"])
    assert rc == 2
    assert "requires a CODE" in capsys.readouterr().out


def test_explain_exit_code_non_integer_returns_usage(capsys) -> None:
    """A non-integer CODE → usage error, exit 2."""
    rc = main(["--explain-exit-code", "notanint"])
    assert rc == 2
    assert "not a valid exit code" in capsys.readouterr().out


def test_explain_exit_code_valid_returns_zero(capsys) -> None:
    rc = main(["--explain-exit-code", "0"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_completion_without_shell_returns_usage(capsys) -> None:
    """`--completion` with no SHELL → usage error, exit 2."""
    rc = main(["--completion"])
    assert rc == 2
    assert "requires a SHELL" in capsys.readouterr().out


def test_notion_print_schema_with_extra_args_returns_usage(capsys) -> None:
    """`--notion-print-database-schema` must be used alone."""
    rc = main(["--notion-print-database-schema", "extra"])
    assert rc == 2
    assert "cannot be combined" in capsys.readouterr().out


def test_help_lists_template_flags() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    assert "--template" in out
    assert "--template-organization" in out
    assert "--template-overwrite-reserved" not in out
