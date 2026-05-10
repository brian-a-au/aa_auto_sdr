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


def test_documented_long_flags_exist_in_parser():
    """Every ``--long-flag`` referenced in AGENTS.md must be a real CLI option.

    Catches the doc-drift class where the contract describes flags that don't
    exist (e.g. an earlier draft mentioned a non-existent ``--snapshot-dir``).
    A small allow-list covers placeholders and documentation-only tokens
    (e.g. ``--format`` values or shell-prompt examples).
    """
    from aa_auto_sdr.cli.parser import build_parser

    parser = build_parser()
    real_flags = {opt for action in parser._actions for opt in action.option_strings if opt.startswith("--")}

    text = AGENTS_MD.read_text()
    # Match `--word-with-hyphens` (anchor on word boundary, allow trailing words like A=, B=)
    documented = set(re.findall(r"--[a-z][a-z0-9-]+", text))

    # Allow-list: tokens that look like flags but are placeholders or values.
    # `--format` values like `json|csv|markdown|excel|html|all|reports|data|ci|pr-comment`
    # and config / value placeholders that share the `--` prefix syntactically.
    # Allow-list — only fast-path flags handled in ``__main__.py`` before
    # argparse runs. Everything else must appear on the actual parser.
    allowlist = {
        "--version",
        # Flags explicitly documented in AGENTS.md as *removed* from the v1.8.0
        # roadmap (they appear in the "deliberately removed" prose but were never
        # added to the parser; the doc explains their absence to agent consumers).
        "--continue-on-error",
        "--shared-cache",
        "--use-cache",
        # Flags explicitly documented in AGENTS.md as *removed* from the v1.9.0
        # roadmap (CJA-only concepts or redundant in AA's per-RSID generation;
        # documented to explain their absence to agent consumers).
        "--no-component-types",
        "--lock-stale-threshold",
        "--include-names",
        "--include-metadata",
    }

    missing = documented - real_flags - allowlist
    assert not missing, (
        f"AGENTS.md references flags that don't exist on the parser: {sorted(missing)}. "
        "Either add them to the parser, fix the doc, or add to the allowlist with a comment."
    )
