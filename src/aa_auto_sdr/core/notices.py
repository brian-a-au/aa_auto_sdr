"""One-line notices and warnings on stderr, each printed once per run.

A notice or a warning is one line on stderr. It never goes to stdout, and it
never changes the exit code, so machine output on stdout stays clean. The same
line is printed once per process, however many times the lookup runs (watch
mode and batch runs look the credential up more than once).
"""

from __future__ import annotations

import sys

_printed: set[str] = set()


def say(kind: str, message: str) -> None:
    """Print `<kind>: <message>` on stderr, unless this run already printed it."""
    line = f"{kind}: {message}"
    if line in _printed:
        return
    _printed.add(line)
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def reset() -> None:
    """Forget what was printed. For tests, which share one process."""
    _printed.clear()
