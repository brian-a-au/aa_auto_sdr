#!/usr/bin/env python3
"""Validate version string consistency across project.

Canonical: src/aa_auto_sdr/core/version.py
Verified:
  - pyproject.toml dynamic version wired to canonical path
  - CHANGELOG.md most-recent ## [x.y.z] heading matches

Exits 0 on match, 1 on first mismatch."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _read_canonical(repo: Path) -> str:
    text = (repo / "src" / "aa_auto_sdr" / "core" / "version.py").read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        print("error: could not parse __version__ from core/version.py", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def _check_pyproject(repo: Path) -> None:
    text = (repo / "pyproject.toml").read_text()
    if 'dynamic = ["version"]' not in text:
        print('error: pyproject.toml missing dynamic = ["version"]', file=sys.stderr)
        sys.exit(1)
    if 'path = "src/aa_auto_sdr/core/version.py"' not in text:
        print("error: pyproject.toml [tool.hatch.version] path mismatch", file=sys.stderr)
        sys.exit(1)


def _check_changelog(repo: Path, canonical: str) -> None:
    """The most recent released heading (`## [x.y.z]`, skipping Unreleased) must match.

    Searched across the whole file, so a long Unreleased section never hides it."""
    text = (repo / "CHANGELOG.md").read_text()
    match = re.search(r"^## \[(\d+\.\d+\.\d+[^\]]*)\]", text, re.MULTILINE)
    if match is None:
        print("error: CHANGELOG.md has no released '## [x.y.z]' heading", file=sys.stderr)
        sys.exit(1)
    if match.group(1) != canonical:
        print(
            f"error: CHANGELOG.md most recent release heading is '## [{match.group(1)}]', expected '## [{canonical}]'",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> int:
    repo = Path.cwd()
    canonical = _read_canonical(repo)
    _check_pyproject(repo)
    _check_changelog(repo, canonical)
    print(f"version sync OK: {canonical}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
