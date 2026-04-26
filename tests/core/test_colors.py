"""ANSI color helpers — auto-disabled for non-TTY stdout or NO_COLOR=1."""

import pytest

from aa_auto_sdr.core import colors


def _force_enabled(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    """Bypass the TTY/NO_COLOR check for deterministic tests."""
    monkeypatch.setattr(colors, "_enabled", lambda: enabled)


def test_bold_when_enabled_wraps_in_ansi(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, True)
    assert colors.bold("hi") == "\033[1mhi\033[0m"


def test_bold_when_disabled_returns_text_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, False)
    assert colors.bold("hi") == "hi"


def test_success_when_enabled_uses_green(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, True)
    assert colors.success("ok") == "\033[32mok\033[0m"


def test_success_when_disabled_returns_text_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, False)
    assert colors.success("ok") == "ok"


def test_error_when_enabled_uses_red(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, True)
    assert colors.error("nope") == "\033[31mnope\033[0m"


def test_error_when_disabled_returns_text_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, False)
    assert colors.error("nope") == "nope"


def test_status_ok_true_uses_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, True)
    assert colors.status(True, "100%") == colors.success("100%")


def test_status_ok_false_uses_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, True)
    assert colors.status(False, "80%") == colors.error("80%")


def test_no_color_env_disables_colors_even_when_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """NO_COLOR=anything overrides a TTY stdout, per https://no-color.org/."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)  # pretend we're on a real TTY
    # Don't patch _enabled — exercise the real implementation.
    assert colors.bold("hi") == "hi"
    assert colors.success("ok") == "ok"
    assert colors.error("nope") == "nope"


def test_tty_with_no_color_unset_enables_colors(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real TTY without NO_COLOR set should produce ANSI escapes."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert colors.bold("hi") == "\033[1mhi\033[0m"


def test_non_tty_disables_colors(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdout.isatty() False (e.g. piping into another command) disables colors."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert colors.bold("hi") == "hi"


def test_warn_when_enabled_uses_yellow(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, True)
    assert colors.warn("careful") == "\033[33mcareful\033[0m"


def test_warn_when_disabled_returns_text_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_enabled(monkeypatch, False)
    assert colors.warn("careful") == "careful"
