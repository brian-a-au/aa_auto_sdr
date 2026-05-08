"""AGENTS.md canonical sections + key tables present (spec §4.6, §7)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def test_agents_md_exists():
    assert AGENTS_MD.exists(), "AGENTS.md must live at repo root"


CANONICAL_HEADINGS = [
    "# AGENTS.md",  # title
    "## Setup",
    "## Command Reference",
    "## Exit Codes",
    "## Output Conventions",
    "## File Conventions",
    "## Agent Integration",
    "## See Also",
]


@pytest.mark.parametrize("heading", CANONICAL_HEADINGS)
def test_canonical_heading_present(heading):
    text = AGENTS_MD.read_text()
    # Match headings at line start (multiline)
    pattern = rf"^{re.escape(heading)}"
    assert re.search(pattern, text, re.MULTILINE), f"Missing heading: {heading}"


REQUIRED_EXIT_CODES = [
    "`0`",
    "`1`",
    "`2`",
    "`3`",
    "`10`",
    "`11`",
    "`12`",
    "`13`",
    "`14`",
    "`15`",
    "`16`",
    "`130`",
]


@pytest.mark.parametrize("code", REQUIRED_EXIT_CODES)
def test_exit_code_present(code):
    text = AGENTS_MD.read_text()
    assert code in text, f"Missing exit-code entry: {code}"


REQUIRED_APPLICABILITY_ROWS = [
    "Single SDR",
    "Batch SDR",
    "Discovery / Inspection",
    "Diff Family",
    "Stats",
    "Validation / Preflight",
    "Fast-Path Flags",
    "Snapshots",
]


@pytest.mark.parametrize("row", REQUIRED_APPLICABILITY_ROWS)
def test_applicability_row_present(row):
    text = AGENTS_MD.read_text()
    assert row in text, f"Missing applicability row: {row}"


def test_agent_mode_preset_definition_present():
    text = AGENTS_MD.read_text()
    assert "--format json --output - --log-format json" in text


def test_read_only_invariant_stated():
    text = AGENTS_MD.read_text()
    assert "Read-only" in text or "read-only" in text


def test_error_envelope_shape_documented():
    text = AGENTS_MD.read_text()
    assert "error_type" in text
