"""Shared atomic file-output primitives."""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

_STAGING_ATTEMPTS = 100


def _create_staging_path(destination: Path) -> Path:
    """Create and close a unique sibling file suitable for serialization."""
    existing_mode: int | None = None
    try:
        destination_stat = destination.stat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISREG(destination_stat.st_mode):
            existing_mode = stat.S_IMODE(destination_stat.st_mode)

    suffix = destination.suffix or ".tmp"
    prefix = f".{destination.stem}."
    for _ in range(_STAGING_ATTEMPTS):
        staged = destination.parent / f"{prefix}{secrets.token_hex(8)}{suffix}"
        try:
            fd = os.open(staged, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o666)
        except FileExistsError:
            continue

        try:
            if existing_mode is not None:
                os.chmod(staged, existing_mode)
            os.close(fd)
        except BaseException:
            with suppress(OSError):
                os.close(fd)
            staged.unlink(missing_ok=True)
            raise
        return staged

    raise FileExistsError(f"Unable to allocate staging file for {destination}")


def atomic_write_path[T](destination: Path, serializer: Callable[[Path], T]) -> T:
    """Serialize to a sibling staging path, then atomically replace destination.

    The destination's parent must already exist. The staging path retains the
    destination suffix and is closed before ``serializer`` receives it.
    """
    staged = _create_staging_path(destination)
    try:
        result = serializer(staged)
        os.replace(staged, destination)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return result


def atomic_write_text(
    destination: Path,
    content: str,
    *,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> None:
    """Write text through :func:`atomic_write_path` without creating parents."""

    def write(staged: Path) -> None:
        with staged.open("w", encoding=encoding, errors=errors, newline=newline) as handle:
            handle.write(content)

    atomic_write_path(destination, write)
