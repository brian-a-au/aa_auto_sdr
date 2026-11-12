"""Meta-test: `import aanalytics2` only inside src/aa_auto_sdr/api/client.py.

Master design spec §3 + CLAUDE.md: SDK isolation is a load-bearing rule. This
test fails CI if any other source file imports aanalytics2."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr"
_PATTERN = re.compile(r"^\s*(import\s+aanalytics2|from\s+aanalytics2\b)", re.MULTILINE)
_ALLOWED = frozenset({SRC / "api" / "client.py"})


def _violations(files: Iterable[tuple[Path, str]]) -> list[str]:
    found: list[str] = []
    for py, text in files:
        if py in _ALLOWED:
            continue
        if _PATTERN.search(text):
            found.append(str(py.relative_to(SRC)))
    return found


def test_sdk_import_outside_client_is_reported() -> None:
    fake = SRC / "api" / "fetch.py"
    assert _violations([(fake, "import aanalytics2\n")]) == [str(fake.relative_to(SRC))]
    assert _violations([(SRC / "api" / "client.py", "import aanalytics2\n")]) == []


def test_no_aanalytics2_outside_api() -> None:
    violations = _violations((py, py.read_text(encoding="utf-8")) for py in SRC.rglob("*.py"))
    assert not violations, (
        f"aanalytics2 imported outside api/client.py: {violations}\n"
        "SDK isolation rule: only api/client.py may import aanalytics2."
    )
