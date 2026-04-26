"""ANSI color helpers. Auto-disabled for non-TTY stdout or NO_COLOR set.

See https://no-color.org/ for the NO_COLOR convention.

Public API: bold(), success(), error(), status(ok, text). The reusable wrappers
will be picked up by v0.7's snapshot/diff renderer too."""

from __future__ import annotations

import os
import sys

_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"


def _enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _wrap(text: str, code: str) -> str:
    if not _enabled():
        return text
    return f"{code}{text}{_RESET}"


def bold(text: str) -> str:
    return _wrap(text, _BOLD)


def success(text: str) -> str:
    return _wrap(text, _GREEN)


def error(text: str) -> str:
    return _wrap(text, _RED)


def warn(text: str) -> str:
    return _wrap(text, _YELLOW)


def status(ok: bool, text: str) -> str:
    """Green if ok, red otherwise. Used for the success-rate line in the summary banner."""
    return success(text) if ok else error(text)
