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
    if not path.exists():
        raise ConfigError(f"Profile '{name}' not found at {path}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    logger.debug("profile read")
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
    if not root.exists():
        logger.debug("list_profiles count=0", extra={"count": 0})
        return []
    out = sorted(p.name for p in root.iterdir() if p.is_dir())
    logger.debug("list_profiles count=%s", len(out), extra={"count": len(out)})
    return out
