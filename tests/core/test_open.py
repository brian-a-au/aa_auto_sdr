"""Cross-platform file open helper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from aa_auto_sdr.core._open import os_open


def test_macos_uses_open(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")
    with patch("subprocess.run") as run:
        os_open(Path("/tmp/x.xlsx"))
        run.assert_called_once()
        args = run.call_args[0][0]
        assert args[0] == "open"


def test_linux_uses_xdg_open(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    with patch("subprocess.run") as run:
        os_open(Path("/tmp/x.xlsx"))
        run.assert_called_once()
        args = run.call_args[0][0]
        assert args[0] == "xdg-open"


def test_windows_uses_start(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "win32")
    with patch("subprocess.run") as run:
        os_open(Path("C:/tmp/x.xlsx"))
        run.assert_called_once()


def test_failure_does_not_raise(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "darwin")

    def _boom(*_, **__):
        raise OSError("no display")

    with patch("subprocess.run", _boom):
        # Should not raise — best-effort.
        os_open(Path("/tmp/x.xlsx"))
