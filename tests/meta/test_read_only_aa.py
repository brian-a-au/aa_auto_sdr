"""Meta-test: api/ source contains no SDK write-shape calls.

CLAUDE.md: 'No write operations against AA, ever.' Bright-line guarantee
that this tool can never modify a customer's AA environment. The forbidden
verb list is informed by the actual aanalytics2 write surface."""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr" / "api"

# Master spec §6: forbidden verb prefixes followed by Capitalized identifier
# and an open paren. The leading dot anchors against an SDK handle method call.
_WRITE_SHAPE = re.compile(
    r"\.(create|update|delete|put|patch|post|remove|import|save|write|"
    r"share|send|resend|reprocess|commit|disable|enable|renew)[A-Z]\w*\s*\(",
)


def test_no_write_shape_sdk_calls_in_api() -> None:
    violations: list[str] = []
    for py in API.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for match in _WRITE_SHAPE.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            violations.append(f"{py.name}:{line_no}: {match.group(0)}")
    assert not violations, f"SDK write-shape call in api/ — Read-Only AA invariant violated: {violations}"
