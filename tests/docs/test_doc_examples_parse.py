"""Command examples in the docs must be accepted by the real parser."""

from __future__ import annotations

import shlex
from pathlib import Path

from aa_auto_sdr.cli.parser import build_parser

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_MD = REPO_ROOT / "AGENTS.md"


def _example_args(line: str) -> list[str]:
    """Return the arguments after ``aa_auto_sdr`` with placeholders filled in."""
    line = line.replace("<RSID>", "rs1").replace("<name>", "prod")
    tokens = shlex.split(line)
    return tokens[tokens.index("aa_auto_sdr") + 1 :]


def test_agents_md_auto_prune_example_parses():
    lines = [ln for ln in AGENTS_MD.read_text(encoding="utf-8").splitlines() if "--auto-snapshot --auto-prune" in ln]
    assert lines, "AGENTS.md has no --auto-snapshot --auto-prune example"
    for line in lines:
        build_parser().parse_args(_example_args(line))
