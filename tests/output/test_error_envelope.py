"""output/error_envelope.py — JSON error envelope to stderr on pipe-path failures."""

from __future__ import annotations

import json

from aa_auto_sdr.core.exceptions import ApiError, AuthError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.error_envelope import emit_error_envelope


def test_emit_error_envelope_writes_to_stderr(capsys) -> None:
    emit_error_envelope(AuthError("bad creds"), ExitCode.AUTH.value)
    captured = capsys.readouterr()
    assert captured.out == ""  # stdout silent
    assert captured.err  # something on stderr


def test_emit_error_envelope_is_valid_json(capsys) -> None:
    emit_error_envelope(AuthError("bad creds"), ExitCode.AUTH.value)
    line = capsys.readouterr().err.strip()
    payload = json.loads(line)
    assert payload["error"]["code"] == 11
    assert payload["error"]["type"] == "AuthError"
    assert payload["error"]["message"] == "bad creds"
    assert "hint" in payload["error"]


def test_emit_error_envelope_hint_for_known_code(capsys) -> None:
    """Hint is sourced from EXPLANATIONS first 'What to try' suggestion."""
    emit_error_envelope(AuthError("x"), ExitCode.AUTH.value)
    payload = json.loads(capsys.readouterr().err.strip())
    hint = payload["error"]["hint"].lower()
    assert "credentials" in hint or "scopes" in hint or "verify" in hint


def test_emit_error_envelope_for_api_error(capsys) -> None:
    emit_error_envelope(ApiError("rate limited"), ExitCode.API.value)
    payload = json.loads(capsys.readouterr().err.strip())
    assert payload["error"]["type"] == "ApiError"
    assert payload["error"]["code"] == 12


def test_emit_error_envelope_one_line(capsys) -> None:
    """Output must be a single line (machine-readable, jq-friendly)."""
    emit_error_envelope(AuthError("multi\nline\nmessage"), ExitCode.AUTH.value)
    err = capsys.readouterr().err
    assert err.count("\n") == 1  # one trailing newline only
