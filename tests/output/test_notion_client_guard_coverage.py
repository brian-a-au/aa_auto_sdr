"""Targeted coverage for notion_client_guard import guards.

Covers the missing-dotenv swallow in `_maybe_load_dotenv` and both branches of
`_require_notion_client` (client returned vs. install-instructions exit)."""

from __future__ import annotations

import sys
import types

import pytest

from aa_auto_sdr.output import notion_client_guard as guard


def test_maybe_load_dotenv_swallows_missing_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # Setting the module to None makes `from dotenv import load_dotenv` raise
    # ImportError, which the guard must swallow silently.
    monkeypatch.setitem(sys.modules, "dotenv", None)
    guard._maybe_load_dotenv()  # must not raise


def test_require_notion_client_returns_client_class(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("notion_client")

    class _FakeClient:
        pass

    fake.Client = _FakeClient
    monkeypatch.setitem(sys.modules, "notion_client", fake)
    assert guard._require_notion_client() is _FakeClient


def test_require_notion_client_exits_when_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "notion_client", None)
    with pytest.raises(SystemExit) as exc:
        guard._require_notion_client()
    assert exc.value.code == 1
    assert "notion extra" in capsys.readouterr().err
