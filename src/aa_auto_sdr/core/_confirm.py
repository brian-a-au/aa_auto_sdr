"""Confirmation prompt helper. Skip when assume_yes or stdin is non-interactive."""

from __future__ import annotations

import sys


def confirm(message: str, *, assume_yes: bool = False) -> bool:
    """Ask the user to confirm. Returns True iff user types 'y'/'yes'.

    If `assume_yes` is True, returns True without prompting.
    If stdin is non-interactive (piped, CI), returns False without prompting
    (refuse to proceed when no human can answer)."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    response = input(f"{message} [y/N] ").strip().lower()
    return response in ("y", "yes")
