"""core/colors.set_theme() switches added/removed ANSI palettes."""

from __future__ import annotations

import pytest

from aa_auto_sdr.core import colors


@pytest.fixture(autouse=True)
def _reset_theme():
    yield
    colors.set_theme("default")


def _force_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(colors, "_enabled", lambda: True)


def test_default_theme_uses_green_for_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("default")
    assert colors.success("ok").startswith("\033[32m")


def test_default_theme_uses_red_for_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("default")
    assert colors.error("nope").startswith("\033[31m")


def test_accessible_theme_uses_blue_for_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("accessible")
    assert colors.success("ok").startswith("\033[34m")


def test_accessible_theme_uses_orange_for_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("accessible")
    assert colors.error("nope").startswith("\033[38;5;208m")


def test_invalid_theme_silently_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("default")
    colors.set_theme("neon")  # must not raise; theme stays "default"
    assert colors.success("ok").startswith("\033[32m")


def test_bold_unchanged_under_accessible(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("accessible")
    assert colors.bold("title") == "\033[1mtitle\033[0m"


def test_warn_unchanged_under_accessible(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch)
    colors.set_theme("accessible")
    assert colors.warn("hmm").startswith("\033[33m")
