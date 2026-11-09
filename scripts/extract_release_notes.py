#!/usr/bin/env python3
"""Write the CHANGELOG.md section for one version to a file.

The release workflow uses the output as the GitHub Release body. The section
is everything after the `## [X.Y.Z]` heading up to the next `## ` heading.

Exits 0 on success, 1 when the section is missing or empty.

Usage: extract_release_notes.py X.Y.Z OUTPUT [--changelog PATH]"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def extract(changelog: str, version: str) -> str:
    """Return the body of the `## [version]` section, stripped of blank edges."""
    heading = re.compile(rf"^## \[{re.escape(version)}\](?:\s|$)")
    lines = changelog.splitlines()
    start = next((index for index, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ValueError(f"CHANGELOG.md has no '## [{version}]' section")
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    body = "\n".join(lines[start + 1 : end]).strip()
    if not body:
        raise ValueError(f"CHANGELOG.md section '## [{version}]' is empty")
    return body + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    args = parser.parse_args(argv)
    try:
        notes = extract(args.changelog.read_text(encoding="utf-8"), args.version)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")
    print(f"wrote release notes for {args.version} to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
