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


_CLI_COMMANDS_ROOT = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "aa_auto_sdr"
    / "cli"
    / "commands"
)

# Any client.handle.<sdk-method>( from a CLI command file is a layering violation:
# CLI code should consume normalized models from api/fetch.py, not call the SDK
# directly. The remediation is always "add a typed wrapper to api/fetch.py".
_CLI_REACHTHROUGH = re.compile(r"client\.handle\.[a-zA-Z_]\w*\(")


def test_no_sdk_reachthrough_from_cli_commands() -> None:
    """CLI command modules must consume normalized models from api/fetch.py;
    they may not call client.handle.<sdk-method>(...) directly.

    Codifies the architectural rule from CLAUDE.md ("only api/ imports
    aanalytics2"). Any new offender breaks CI with a remediation hint.
    """
    assert _CLI_COMMANDS_ROOT.is_dir(), f"expected {_CLI_COMMANDS_ROOT} to exist"
    py_files = list(_CLI_COMMANDS_ROOT.rglob("*.py"))
    assert py_files, f"no .py files under {_CLI_COMMANDS_ROOT} — scan would be vacuous"
    offenders: list[str] = []
    for py in py_files:
        text = py.read_text(encoding="utf-8")
        for match in _CLI_REACHTHROUGH.finditer(text):
            line = text[: match.start()].count("\n") + 1
            rel = py.relative_to(_CLI_COMMANDS_ROOT.parent.parent)
            offenders.append(f"{rel}:{line}: {match.group()}")
    assert not offenders, (
        "CLI command modules must not reach into client.handle.<sdk> directly. "
        "Add a typed wrapper to api/fetch.py and consume it instead. Offenders:\n  "
        + "\n  ".join(offenders)
    )
