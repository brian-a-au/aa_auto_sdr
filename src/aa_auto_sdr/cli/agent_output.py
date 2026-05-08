"""Per-command-family stdout capability resolution for `--agent-mode`.

Spec §4.2. Diff/discovery/inspect/stats can stream JSON (or CSV for
discovery) on stdout under `--agent-mode`. Generate/batch always write
file artifacts; calling `resolve_agent_output_path` with an empty
`stdout_formats` set is the documented mechanism for these families
to suppress the agent-mode `--output -` default.

Design invariants
-----------------
* Explicit ``--output`` always wins.
* Explicit ``--quiet`` always wins.
* Quiet follows the **effective** stdout destination — not the parser-level
  preset that may have been suppressed for a file-only format.
* Resolvers accept the *exact* ``argv`` that ``cli.main.run`` parsed; they
  never consult ``sys.argv`` when callers pass ``argv`` explicitly. Callers
  that pass ``argv=None`` fall back to ``sys.argv[1:]`` for back-compat.
"""

from __future__ import annotations

import argparse
import functools
from collections.abc import Container

from aa_auto_sdr.cli.option_resolution import explicit_long_option_dests

__all__ = [
    "DIFF_STDOUT_FORMATS",
    "DISCOVERY_STDOUT_FORMATS",
    "STATS_STDOUT_FORMATS",
    "is_stdout_path",
    "resolve_agent_output_path",
    "resolve_agent_quiet",
]


DIFF_STDOUT_FORMATS: frozenset[str] = frozenset({"json"})
"""Diff formats that may emit directly to stdout under `--agent-mode`."""

DISCOVERY_STDOUT_FORMATS: frozenset[str] = frozenset({"json", "csv"})
"""Discovery / inspection formats stdout-capable under the contract."""

STATS_STDOUT_FORMATS: frozenset[str] = frozenset({"json"})
"""Stats formats stdout-capable under the contract.

Reserved: ``cli/commands/stats.py`` currently has no ``--output`` parameter
and prints directly to stdout, so this constant is *not* consumed by any
production call site today. It exists for symmetry with
``DIFF_STDOUT_FORMATS`` / ``DISCOVERY_STDOUT_FORMATS`` and to future-proof
the contract if stats grows an ``--output`` flag later. Per spec §4.2."""


_STDOUT_ALIASES: frozenset[str] = frozenset({"-", "stdout"})
"""Case-sensitive — matches the lowercase Unix convention. Anything else
(``"STDOUT"``, ``"Stdout"``, ``"/dev/stdout"``) is treated as a file path."""


def is_stdout_path(path: str | None) -> bool:
    """Return whether *path* is the canonical stdout sentinel ``"-"`` or
    ``"stdout"`` (case-sensitive)."""
    return path in _STDOUT_ALIASES


@functools.cache
def _known_long_options() -> frozenset[str]:
    """Lazily-built (and memoized) set of every ``--…`` option exposed by
    ``cli.parser.build_parser``. Cached because rebuilding the parser per
    resolver call wastes ~1.2 ms each."""
    from aa_auto_sdr.cli.parser import build_parser

    parser = build_parser()
    return frozenset(
        option for action in parser._actions for option in action.option_strings if option.startswith("--")
    )


def _option_was_explicit(option: str, argv: list[str] | None) -> bool:
    """Return whether *option* appears on *argv*.

    *argv* should be the same list passed to ``cli.main.run`` so the
    resolver sees exactly what the parser saw. ``None`` falls back to
    ``sys.argv[1:]`` (only safe when called outside ``run``)."""
    dests = explicit_long_option_dests(
        argv,
        tracked_options=frozenset({option}),
        known_long_options=_known_long_options(),
    )
    return option.removeprefix("--").replace("-", "_") in dests


def resolve_agent_output_path(
    args: argparse.Namespace,
    *,
    argv: list[str] | None = None,
    output_format: str,
    stdout_formats: Container[str],
) -> str | None:
    """Resolve the effective output path after agent-mode default application.

    Returns ``args.output`` unchanged when:
    * ``--agent-mode`` is not active,
    * ``--output`` was explicit on *argv*, or
    * ``output_format`` is in *stdout_formats*.

    Otherwise returns ``None`` to signal that the inherited agent-mode
    ``--output -`` default should be suppressed (file-only family).
    """
    output_path = getattr(args, "output", None)

    if not getattr(args, "agent_mode", False):
        return output_path

    if _option_was_explicit("--output", argv):
        return output_path

    if output_format in stdout_formats:
        return output_path

    return None


def resolve_agent_quiet(
    args: argparse.Namespace,
    *,
    argv: list[str] | None = None,
    output_path: str | None,
) -> bool:
    """Resolve the effective quiet flag from the **resolved** output path.

    Explicit ``--quiet`` always wins. Otherwise quiet is derived solely
    from whether the effective output destination still targets stdout
    (or whether ``--run-summary-json -`` is in effect).
    """
    if _option_was_explicit("--quiet", argv):
        return True

    if is_stdout_path(getattr(args, "run_summary_json", None)):
        return True

    return is_stdout_path(output_path)
