"""Bright-line guarantee that aa_auto_sdr never writes to a customer's AA org.

Scans src/aa_auto_sdr/api/ for SDK method calls matching write-shape patterns.
This is non-negotiable per the design spec — never relax this rule.
"""

import re
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "aa_auto_sdr" / "api"

# Forbidden verb prefixes followed by Capitalized identifier (typical SDK style).
# The denylist is informed by the actual aanalytics2 write surface, including
# non-obvious writers like shareComponent, sendDataToDataSource, commitImportClassificationJob,
# disableAlert, enableAlert, renewAlerts, reprocessDataFeedRequest. See spike findings §9.
_FORBIDDEN = re.compile(
    r"\.(create|update|delete|put|patch|post|remove|import|save|write|share|send|resend|reprocess|commit|disable|enable|renew)[A-Z]\w*\s*\(",
)

# Substrings indicating legacy 1.4 endpoint paths.
_API_14_HINTS = ("/api/1.4/", "1.4/segments", "1.4/calculatedmetrics", "/v14/")


def _api_source_files() -> list[Path]:
    return [p for p in _API_ROOT.rglob("*.py") if p.is_file()]


def test_api_root_exists() -> None:
    assert _API_ROOT.is_dir(), f"expected {_API_ROOT} to exist"
    assert _api_source_files(), "no python files under api/"


@pytest.mark.parametrize("path", _api_source_files(), ids=lambda p: p.name)
def test_no_write_shaped_sdk_calls(path: Path) -> None:
    text = path.read_text()
    matches = _FORBIDDEN.findall(text)
    assert not matches, (
        f"{path.name}: forbidden write-shape SDK call(s) detected — verbs={matches}. AA API access must be read-only."
    )


@pytest.mark.parametrize("path", _api_source_files(), ids=lambda p: p.name)
def test_no_legacy_14_endpoint_hints(path: Path) -> None:
    text = path.read_text()
    hits = [hint for hint in _API_14_HINTS if hint in text]
    assert not hits, f"{path.name}: legacy 1.4 endpoint reference detected — {hits}"
