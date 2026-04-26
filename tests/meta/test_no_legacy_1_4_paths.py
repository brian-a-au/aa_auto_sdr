"""Meta-test: api/ source contains no Adobe Analytics 1.4 endpoint substrings.

CLAUDE.md: 'No legacy 1.4 API.' Features that exist only in 1.4 are out of
scope; we surface UnsupportedByApi20 rather than degrade."""

from __future__ import annotations

from pathlib import Path

API = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr" / "api"

# Known 1.4 endpoint substrings. Add to this list if more surface during review.
_LEGACY_PATTERNS = (
    "/api/1.4/",
    "/admin/1.4/",
    "Report.Queue",
    "OmnitureReporting",
)


def test_no_legacy_1_4_endpoint_strings() -> None:
    violations: list[str] = []
    for py in API.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for pattern in _LEGACY_PATTERNS:
            if pattern in text:
                violations.append(f"{py.name}: {pattern!r}")
    assert not violations, (
        f"1.4 API references in api/: {violations}\n"
        "Use only API 2.0; raise UnsupportedByApi20 for missing surface."
    )
