"""Explicit-long-option detection.

Used by `_apply_agent_mode_defaults` to know whether tracked options
were explicitly provided on argv. Recognizes both `--option value`
and `--option=value` forms. Unknown tokens (not in `known_long_options`)
are ignored — argparse's own parsing surfaces those errors elsewhere.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable


def explicit_long_option_dests(
    argv: list[str] | None,
    *,
    tracked_options: Iterable[str],
    known_long_options: Iterable[str],
) -> set[str]:
    """Return the dest names (hyphens replaced with underscores) of tracked
    long options that appear explicitly on argv.

    Args:
        argv: Argv list to inspect. None defaults to ``sys.argv[1:]``.
        tracked_options: Long options of interest (e.g. ``{"--format", "--output"}``).
        known_long_options: All long options the parser recognizes; used to
            filter out unknown tokens.
    """
    tokens = sys.argv[1:] if argv is None else argv
    tracked = frozenset(tracked_options)
    known = frozenset(known_long_options)

    found: set[str] = set()
    for token in tokens:
        if not token.startswith("--"):
            continue
        # --option=value form
        if "=" in token:
            name = token.split("=", 1)[0]
        else:
            name = token
        if name not in known:
            continue
        if name in tracked:
            dest = name.removeprefix("--").replace("-", "_")
            found.add(dest)
    return found
