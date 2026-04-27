"""--exit-codes and --explain-exit-code <CODE> handlers."""

from __future__ import annotations

from aa_auto_sdr.cli.commands.exit_codes import run_explain_exit_code, run_list_exit_codes
from aa_auto_sdr.core.exit_codes import ROWS


def test_run_list_exit_codes_prints_table(capsys) -> None:
    rc = run_list_exit_codes()
    assert rc == 0
    out = capsys.readouterr().out
    assert "Code" in out
    assert "Meaning" in out
    for code, meaning in ROWS:
        assert str(code.value) in out
        assert meaning in out


def test_run_list_exit_codes_mentions_explain_pointer(capsys) -> None:
    run_list_exit_codes()
    out = capsys.readouterr().out
    assert "--explain-exit-code" in out


def test_run_explain_exit_code_known(capsys) -> None:
    rc = run_explain_exit_code(11)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Exit code 11" in out
    assert "Adobe OAuth" in out  # from EXPLANATIONS[ExitCode.AUTH]
    assert "What to try:" in out


def test_run_explain_exit_code_zero(capsys) -> None:
    rc = run_explain_exit_code(0)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Exit code 0" in out
    assert "succeeded" in out.lower()


def test_run_explain_exit_code_unknown_returns_2(capsys) -> None:
    rc = run_explain_exit_code(999)
    assert rc == 2
    captured = capsys.readouterr()
    err = captured.out + captured.err
    assert "999" in err
    assert "unknown exit code" in err.lower() or "--exit-codes" in err


def test_explain_exit_code_config_mentions_v1_1_scenarios(capsys) -> None:
    """v1.1 added --list-snapshots / --prune-snapshots / --profile-test etc.
    The CONFIG explanation should mention them so users get a remediation hint."""
    rc = run_explain_exit_code(10)
    assert rc == 0
    out = capsys.readouterr().out
    assert "--list-snapshots" in out or "--profile-test" in out
    assert "--keep-since" in out or "--keep-last" in out


def test_explain_exit_code_auth_mentions_profile_test(capsys) -> None:
    """v1.1 added --profile-test. The AUTH explanation should reference it."""
    rc = run_explain_exit_code(11)
    assert rc == 0
    out = capsys.readouterr().out
    assert "--profile-test" in out


def test_explain_exit_code_warn(capsys) -> None:
    """v1.2 — exit code 3 (WARN) for diff --warn-threshold exceeded."""
    rc = run_explain_exit_code(3)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Exit code 3" in out
    assert "warn-threshold" in out.lower()


def test_run_list_exit_codes_includes_warn(capsys) -> None:
    """The exit-codes table now includes 3 WARN."""
    rc = run_list_exit_codes()
    assert rc == 0
    out = capsys.readouterr().out
    assert "3" in out
    assert "warn" in out.lower()
