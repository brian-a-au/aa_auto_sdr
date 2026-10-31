"""Fast-path entry tests — must complete without importing pandas/aanalytics2."""

import subprocess
import sys

from aa_auto_sdr.__main__ import main
from aa_auto_sdr.core.version import __version__


def test_version_flag_short() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert __version__ in result.stdout


def test_version_flag_long() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert __version__ in result.stdout


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
    assert "requires a CODE" in capsys.readouterr().err


def test_explain_exit_code_non_integer_returns_usage(capsys) -> None:
    """A non-integer CODE → usage error, exit 2."""
    rc = main(["--explain-exit-code", "notanint"])
    assert rc == 2
    assert "not a valid exit code" in capsys.readouterr().err


def test_explain_exit_code_valid_returns_zero(capsys) -> None:
    rc = main(["--explain-exit-code", "0"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_completion_without_shell_returns_usage(capsys) -> None:
    """`--completion` with no SHELL → usage error, exit 2."""
    rc = main(["--completion"])
    assert rc == 2
    assert "requires a SHELL" in capsys.readouterr().err


def test_notion_print_schema_with_extra_args_returns_usage(capsys) -> None:
    """`--notion-print-database-schema` must be used alone."""
    rc = main(["--notion-print-database-schema", "extra"])
    assert rc == 2
    assert "cannot be combined" in capsys.readouterr().err


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


def test_help_has_no_version_anchors_or_changelog() -> None:
    """Per CLAUDE.md, user-facing prose does not carry 'added in vX' anchors or
    a changelog block; that history lives in CHANGELOG.md. The help text lists
    what the tool does now."""
    import re

    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = result.stdout
    # No parenthetical version markers like "(v1.2)" or "(v1.13.0)".
    assert not re.search(r"\(v\d+\.\d+", out), "help text still carries a (vX.Y) anchor"
    # No changelog lines like "v1.8.0: ...".
    assert not re.search(r"(?m)^v\d+\.\d+\.\d+:", out), "help text still carries a changelog block"
    # The section headers no longer carry version parentheticals either.
    assert "Batch parallelism:" in out
    assert "Watch mode:" in out
    # Flags are still documented.
    assert "--git-commit" in out
    assert "--template " in out


def test_exit_codes_with_trailing_modifier_rejected(capsys) -> None:
    """`--exit-codes --git-commit` must not silently ignore the modifier; the
    fast path should defer to the parser + validators, which reject it (USAGE)."""
    rc = main(["--exit-codes", "--git-commit"])
    assert rc == 2


def test_completion_with_trailing_modifier_rejected(capsys) -> None:
    rc = main(["--completion", "bash", "--git-commit"])
    assert rc == 2


def test_explain_exit_code_with_trailing_modifier_rejected(capsys) -> None:
    rc = main(["--explain-exit-code", "0", "--git-commit"])
    assert rc == 2


def test_exit_codes_standalone_still_fast_paths(capsys) -> None:
    """The common standalone form is unaffected."""
    rc = main(["--exit-codes"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


def test_help_lists_render_from() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--render-from TOKEN" in result.stdout


def _cp1252_env(tmp_path) -> dict[str, str]:
    import os

    # A Windows console redirected to a file or pipe on Python 3.11-3.14.
    env = {k: v for k, v in os.environ.items() if k not in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE")}
    env.update(HOME=str(tmp_path), PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    env.update(ORG_ID="o@AdobeOrg", CLIENT_ID="c", SECRET="s", SCOPES="openid")
    return env


def test_config_status_on_cp1252_stdout_does_not_crash(tmp_path) -> None:
    # The chain markers (U+2713, U+2298) are not in cp1252; printing them
    # raised UnicodeEncodeError and exited 1.
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--config-status", "--quiet"],
        capture_output=True,
        cwd=tmp_path,
        env=_cp1252_env(tmp_path),
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"\\u2713" in result.stdout or b"\\u2298" in result.stdout


def _cp1252_stdout(monkeypatch):
    import io

    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)
    return buf, stream


def test_soften_lets_watch_event_with_astral_char_through(monkeypatch) -> None:
    # Review focus: a character outside the BMP becomes \U0001f4ca, which is
    # not a JSON escape, but the loop keeps running instead of crashing.
    from aa_auto_sdr.__main__ import _soften_stdout_errors
    from aa_auto_sdr.output.watch_event import StdoutEmitter

    buf, stream = _cp1252_stdout(monkeypatch)
    _soften_stdout_errors()
    StdoutEmitter().emit({"event": "error", "error": "Łódź 📊"})
    assert stream.errors == "backslashreplace"
    assert b"\\u0141" in buf.getvalue()


def test_soften_leaves_utf8_stdout_alone(monkeypatch) -> None:
    import io

    from aa_auto_sdr.__main__ import _soften_stdout_errors

    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    calls: list[dict] = []
    monkeypatch.setattr(stream, "reconfigure", lambda **kw: calls.append(kw), raising=False)
    monkeypatch.setattr(sys, "stdout", stream)
    _soften_stdout_errors()
    assert calls == []


def test_soften_ignores_an_unknown_stdout_encoding(monkeypatch) -> None:
    from aa_auto_sdr.__main__ import _soften_stdout_errors

    class OddStream:
        encoding = "no-such-codec"
        errors = "strict"

        def __init__(self) -> None:
            self.calls: list[dict] = []

        def reconfigure(self, **kw) -> None:
            self.calls.append(kw)

    stream = OddStream()
    monkeypatch.setattr(sys, "stdout", stream)
    _soften_stdout_errors()
    assert stream.calls == []
