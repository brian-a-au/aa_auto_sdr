"""Meta-test: only core/logging.py instantiates handlers / calls
basicConfig / dictConfig / fileConfig.

`logging.getLogger(__name__)` and `import logging` are allowed everywhere
(modules need to obtain a logger). The forbidden pattern is configuring
the logging framework anywhere except the dedicated boundary module."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr"
ALLOWED = SRC / "core" / "logging.py"

_FORBIDDEN_PATTERNS = [
    re.compile(r"\blogging\.basicConfig\b"),
    re.compile(r"\blogging\.config\.(dict|file)Config\b"),
    re.compile(r"\blogging\.FileHandler\b"),
    re.compile(r"\blogging\.handlers\."),
    re.compile(r"\bRotatingFileHandler\b"),
]


def test_no_logging_instantiation_outside_core_logging() -> None:
    violations: list[tuple[str, str]] = []
    for py in SRC.rglob("*.py"):
        if py.resolve() == ALLOWED.resolve():
            continue
        text = py.read_text(encoding="utf-8")
        violations.extend(
            (str(py.relative_to(SRC)), pattern.pattern) for pattern in _FORBIDDEN_PATTERNS if pattern.search(text)
        )
    assert not violations, (
        f"logging-framework instantiation found outside core/logging.py: {violations}\n"
        "Only core/logging.py may configure handlers / formatters / framework state."
    )
