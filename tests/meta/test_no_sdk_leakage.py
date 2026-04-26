"""Meta-test: `import aanalytics2` only inside src/aa_auto_sdr/api/.

Master design spec §3 + CLAUDE.md: SDK isolation is a load-bearing rule. This
test fails CI if any non-api/ source imports aanalytics2."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr"
_PATTERN = re.compile(r"^\s*(import\s+aanalytics2|from\s+aanalytics2\b)", re.MULTILINE)
_ALLOWED_PARENT = SRC / "api"


def test_no_aanalytics2_outside_api() -> None:
    violations: list[str] = []
    for py in SRC.rglob("*.py"):
        if _ALLOWED_PARENT in py.parents:
            continue
        text = py.read_text(encoding="utf-8")
        if _PATTERN.search(text):
            violations.append(str(py.relative_to(SRC)))
    assert not violations, (
        f"aanalytics2 imported outside api/: {violations}\n"
        "SDK isolation rule: only api/client.py and api/fetch.py may import aanalytics2."
    )
