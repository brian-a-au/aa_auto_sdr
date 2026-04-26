"""--completion {bash,zsh,fish} handler."""

from aa_auto_sdr.cli.commands.completion import run_completion


def test_run_completion_bash(capsys) -> None:
    rc = run_completion("bash")
    assert rc == 0
    out = capsys.readouterr().out
    # Bash completion uses `complete -F`
    assert "complete -F" in out
    assert "aa_auto_sdr" in out


def test_run_completion_zsh(capsys) -> None:
    rc = run_completion("zsh")
    assert rc == 0
    out = capsys.readouterr().out
    # Zsh completion uses #compdef
    assert "#compdef aa_auto_sdr" in out or "compdef" in out


def test_run_completion_fish(capsys) -> None:
    rc = run_completion("fish")
    assert rc == 0
    out = capsys.readouterr().out
    # Fish uses `complete -c`
    assert "complete -c aa_auto_sdr" in out


def test_run_completion_lists_action_flags(capsys) -> None:
    """Every action flag should appear in each shell's completion.

    Fish completion strips the leading `--` (using `-l flag` syntax), so
    we look for the flag suffix without the dashes."""
    for shell in ("bash", "zsh", "fish"):
        run_completion(shell)
        out = capsys.readouterr().out
        for flag in (
            "list-reportsuites",
            "describe-reportsuite",
            "diff",
            "batch",
            "snapshot",
            "profile",
            "exit-codes",
        ):
            assert flag in out, f"{flag} missing from {shell} completion"


def test_run_completion_unknown_shell_returns_2(capsys) -> None:
    rc = run_completion("powershell")
    assert rc == 2
