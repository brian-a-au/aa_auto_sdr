#!/usr/bin/env python3
"""Validate version string consistency across project.

Canonical: src/aa_auto_sdr/core/version.py
Verified:
  - pyproject.toml dynamic version wired to canonical path
  - CHANGELOG.md most-recent ## [x.y.z] heading matches
  - README.md status line includes vMAJOR.MINOR

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
    text = (repo / "CHANGELOG.md").read_text()
    head = "\n".join(text.splitlines()[:100])
    if f"## [{canonical}]" not in head:
        print(
            f"error: CHANGELOG.md first 100 lines missing '## [{canonical}]' heading",
            file=sys.stderr,
        )
        sys.exit(1)


def _check_readme(repo: Path, canonical: str) -> None:
    major_minor = ".".join(canonical.split(".")[:2])
    text = (repo / "README.md").read_text()
    if f"v{major_minor}" not in text:
        print(
            f"error: README.md does not mention v{major_minor}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> int:
    repo = Path.cwd()
    canonical = _read_canonical(repo)
    _check_pyproject(repo)
    _check_changelog(repo, canonical)
    _check_readme(repo, canonical)
    print(f"version sync OK: {canonical}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
