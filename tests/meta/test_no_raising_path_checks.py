"""Meta-test: src/ uses `os.path` existence checks, not the pathlib methods.

Before Python 3.14, `Path.exists()`, `is_dir()`, `is_file()`, and
`is_symlink()` raise `PermissionError` when a parent directory can't be
searched; 3.14 returns False. The `os.path` forms return False on every
supported version (3.11+), so a user-chosen path under a locked directory
reads as missing instead of crashing. Behavior tests live in
`tests/test_unsearchable_parent_paths.py`."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr"

_RAISING_CHECK = re.compile(r"\.(exists|is_dir|is_file|is_symlink)\(\)")


def test_no_pathlib_existence_checks_in_src() -> None:
    violations: list[str] = []
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for match in _RAISING_CHECK.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            violations.append(f"{py.relative_to(SRC)}:{line_no}: {match.group(0)}")
    assert not violations, (
        "pathlib existence check in src/ raises PermissionError before Python 3.14; "
        f"use os.path.exists/isdir/isfile/islink instead: {violations}"
    )
