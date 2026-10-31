"""Profile CRUD under <base>/orgs/<name>/config.json."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.json_io import write_json

logger = logging.getLogger(__name__)


def default_base() -> Path:
    """Default profile root: ~/.aa/"""
    return Path(os.environ.get("HOME", "~")).expanduser() / ".aa"


def _profile_dir(name: str, base: Path | None) -> Path:
    return (base or default_base()) / "orgs" / name


def read_profile(name: str, *, base: Path | None = None) -> dict[str, Any]:
    """Read a profile's config.json. Raises ConfigError if missing."""
    path = _profile_dir(name, base) / "config.json"
    if not os.path.exists(path):
        raise ConfigError(f"Profile '{name}' not found at {path}")
    data = read_config_object(path, f"Profile '{name}'")
    logger.debug("profile read")
    return data


def read_config_object(path: Path, label: str) -> dict[str, Any]:
    """Read a JSON credentials file that must hold one object.

    A file that cannot be opened, is not UTF-8 JSON, or holds something other
    than an object raises ConfigError (exit 10) naming `label` and the path."""
    try:
        # utf-8-sig: Windows PowerShell 5 writes UTF-8 with a byte-order mark.
        with path.open(encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise ConfigError(f"{label}: could not read {path}: {exc.strerror or exc}") from exc
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        raise ConfigError(f"{label}: {path} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{label}: {path} must hold a JSON object, got {type(data).__name__}")
    return data


def write_profile(name: str, data: dict[str, Any], *, base: Path | None = None) -> Path:
    """Write a profile's config.json (overwrites). Returns the file path."""
    path = _profile_dir(name, base) / "config.json"
    write_json(path, data)
    logger.debug("profile written")
    return path


def list_profiles(*, base: Path | None = None) -> list[str]:
    """List profile names in sorted order."""
    root = (base or default_base()) / "orgs"
    if not os.path.exists(root):
        logger.debug("list_profiles count=0", extra={"count": 0})
        return []
    out = sorted(p.name for p in root.iterdir() if os.path.isdir(p))
    logger.debug("list_profiles count=%s", len(out), extra={"count": len(out)})
    return out
