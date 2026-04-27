"""Confirmation prompt helper."""

from __future__ import annotations

from aa_auto_sdr.core._confirm import confirm


def test_assume_yes_skips_prompt() -> None:
    assert confirm("delete?", assume_yes=True) is True


def test_non_tty_returns_false(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert confirm("delete?", assume_yes=False) is False


def test_yes_response(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert confirm("delete?", assume_yes=False) is True


def test_no_response(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert confirm("delete?", assume_yes=False) is False


def test_empty_response_defaults_no(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert confirm("delete?", assume_yes=False) is False
