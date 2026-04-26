"""Format alias resolution and writer registry.

Writers register themselves by being imported. Callers that need a writer
should call `bootstrap()` first; the pipeline does this in one place."""

from __future__ import annotations

from aa_auto_sdr.output.protocols import Writer

_ALIASES: dict[str, list[str]] = {
    "all": ["excel", "csv", "json", "html", "markdown"],
    "reports": ["excel", "markdown"],
    "data": ["csv", "json"],
    "ci": ["json", "markdown"],
}

_CONCRETE = {"excel", "csv", "json", "html", "markdown"}

_WRITERS: dict[str, Writer] = {}


def resolve_formats(name: str) -> list[str]:
    """Resolve a user-facing format name to one or more concrete format keys."""
    if name in _ALIASES:
        return list(_ALIASES[name])
    if name in _CONCRETE:
        return [name]
    raise KeyError(f"Unknown format or alias: {name!r}")


def register_writer(name: str, writer: Writer) -> None:
    _WRITERS[name] = writer


def get_writer(name: str) -> Writer:
    if name not in _WRITERS:
        raise KeyError(f"No writer registered for format {name!r}")
    return _WRITERS[name]


def bootstrap() -> None:
    """Import the v0.1 writer modules so they self-register.

    Heavy deps (pandas, xlsxwriter) are pulled in here, not at registry import,
    so the fast-path entry stays cheap."""
    from aa_auto_sdr.output.writers import excel as _excel  # noqa: F401
    from aa_auto_sdr.output.writers import json as _json  # noqa: F401
