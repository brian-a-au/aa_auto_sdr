"""Profile CRUD under <base>/orgs/<name>/config.json."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from aa_auto_sdr.core import notices
from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.json_io import write_json

logger = logging.getLogger(__name__)


def default_base() -> Path:
    """Default profile root: ~/.aa/"""
    return Path(os.environ.get("HOME", "~")).expanduser() / ".aa"


_NAME_MAX = 64
_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def validate_profile_name(name: str) -> None:
    """Refuse a name that breaks the profile name rule.

    A name holds letters, digits, dots, underscores and hyphens only. It
    starts with a letter or a digit, and it is 64 characters or fewer.
    Raises ConfigError (exit 10, code `invalid_profile_name`) with the reason."""
    if name == "":
        reason = "the name is empty"
    elif name in (".", ".."):
        reason = "the name cannot be '.' or '..'"
    elif "/" in name or "\\" in name:
        reason = "the name cannot contain '/' or '\\'"
    elif len(name) > _NAME_MAX:
        reason = f"the name is longer than {_NAME_MAX} characters"
    elif not name[0].isascii() or not name[0].isalnum():
        reason = "the name must start with a letter or a digit"
    elif not _NAME_PATTERN.match(name):
        reason = "the name can hold letters, digits, dots, underscores and hyphens only"
    else:
        return
    error = ConfigError(f"invalid profile name '{name}': {reason}")
    error.code = "invalid_profile_name"
    raise error


def _is_one_folder_under_orgs(name: str, base: Path | None) -> bool:
    """True when `name` is one plain folder name, so it cannot leave orgs/."""
    if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
        return False
    orgs = (base or default_base()) / "orgs"
    built = orgs / name
    return built.parent == orgs and built.name == name


def check_profile_name(name: str, *, base: Path | None = None) -> None:
    """Check a profile name before any path is built from it.

    Every command that reads or writes a profile calls this. A name that
    breaks the name rule raises ConfigError. One exception keeps profiles
    working that were created before the rule: a name that is one plain
    folder name and already has a profile is accepted, with one warning."""
    try:
        validate_profile_name(name)
    except ConfigError:
        if not _is_one_folder_under_orgs(name, base) or not os.path.exists(_profile_dir(name, base) / "config.json"):
            raise
        notices.say(
            "warning",
            f"profile name '{name}' breaks the profile name rule (letters, digits, dots, underscores and "
            "hyphens, starting with a letter or a digit, 64 characters or fewer). The profile still works. "
            "Import it again under a new name to remove this warning.",
        )


def _profile_dir(name: str, base: Path | None) -> Path:
    return (base or default_base()) / "orgs" / name


def profile_config_path(name: str, *, base: Path | None = None) -> Path:
    """The path of a profile's config.json. Call `check_profile_name` first."""
    return _profile_dir(name, base) / "config.json"


def read_profile(name: str, *, base: Path | None = None) -> dict[str, Any]:
    """Read a profile's config.json. Raises ConfigError if the name is invalid or the profile is missing."""
    check_profile_name(name, base=base)
    path = _profile_dir(name, base) / "config.json"
    if not os.path.exists(path):
        error = ConfigError(f"Profile '{name}' not found at {path}")
        error.code = "profile_not_found"
        raise error
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
    """Write a profile's config.json (overwrites). Returns the file path.

    New folders are created with mode 0700 and the file is written with mode 0600."""
    check_profile_name(name, base=base)
    path = _profile_dir(name, base) / "config.json"
    _make_private_dirs(path.parent)
    write_json(path, data)
    logger.debug("profile written")
    return path


def _make_private_dirs(folder: Path) -> None:
    """Create `folder` and its missing parents with mode 0700.

    A folder that already exists keeps its mode. Windows ignores the mode."""
    missing: list[Path] = []
    current = folder
    while not os.path.isdir(current) and current != current.parent:
        missing.append(current)
        current = current.parent
    for new_folder in reversed(missing):
        try:
            os.mkdir(new_folder, 0o700)
        except FileExistsError:  # another process created it first
            continue


def readable_by_others(path: Path) -> bool:
    """True when the group or other users can read the file. Always False on Windows.

    The check follows a symlink, so the mode is the mode of the target."""
    if os.name == "nt":
        return False
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return bool(mode & 0o044)


def list_profiles(*, base: Path | None = None) -> list[str]:
    """List profile names in sorted order."""
    root = (base or default_base()) / "orgs"
    if not os.path.exists(root):
        logger.debug("list_profiles count=0", extra={"count": 0})
        return []
    out = sorted(p.name for p in root.iterdir() if os.path.isdir(p))
    logger.debug("list_profiles count=%s", len(out), extra={"count": len(out)})
    return out
