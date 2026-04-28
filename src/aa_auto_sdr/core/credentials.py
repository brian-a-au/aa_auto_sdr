"""OAuth Server-to-Server credentials and resolution.

Resolution chain (highest precedence first) is implemented in `resolve()` —
see Task 10.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aa_auto_sdr.core.exceptions import ConfigError

_REQUIRED_FIELDS = ("org_id", "client_id", "secret", "scopes")


@dataclass(frozen=True, slots=True)
class Credentials:
    """OAuth S2S credentials plus diagnostic source label."""

    org_id: str
    client_id: str
    secret: str
    scopes: str
    source: str  # 'profile:<name>' | 'env' | '.env' | 'config.json'

    def validate(self) -> None:
        """Raise ConfigError if any required field is missing or whitespace-only."""
        missing = [f for f in _REQUIRED_FIELDS if not getattr(self, f).strip()]
        if missing:
            raise ConfigError(f"Missing required credential fields: {', '.join(missing)} (loaded from {self.source})")


def _from_dict(d: dict, source: str) -> Credentials:
    return Credentials(
        org_id=str(d.get("org_id", "")).strip(),
        client_id=str(d.get("client_id", "")).strip(),
        secret=str(d.get("secret", "")).strip(),
        scopes=str(d.get("scopes", "")).strip(),
        source=source,
    )


def _is_complete(c: Credentials) -> bool:
    return all(getattr(c, f).strip() for f in ("org_id", "client_id", "secret", "scopes"))


def _from_env() -> Credentials:
    return _from_dict(
        {
            "org_id": os.environ.get("ORG_ID", ""),
            "client_id": os.environ.get("CLIENT_ID", ""),
            "secret": os.environ.get("SECRET", ""),
            "scopes": os.environ.get("SCOPES", ""),
        },
        source="env",
    )


def _from_dotenv(working_dir: Path) -> Credentials | None:
    """Load .env via python-dotenv if installed; else return None."""
    try:
        from dotenv import dotenv_values  # type: ignore[import-not-found]
    except ImportError:
        return None
    path = working_dir / ".env"
    if not path.exists():
        return None
    values = dotenv_values(path)
    return _from_dict(values, source=".env")


def _from_config_json(working_dir: Path) -> Credentials | None:
    path = working_dir / "config.json"
    if not path.exists():
        return None
    import json as _json

    with path.open(encoding="utf-8") as fh:
        data = _json.load(fh)
    return _from_dict(data, source="config.json")


def _from_profile(name: str, profiles_base: Path | None) -> Credentials:
    from aa_auto_sdr.core import profiles

    data = profiles.read_profile(name, base=profiles_base)
    return _from_dict(data, source=f"profile:{name}")


def resolve(
    *,
    profile: str | None = None,
    profiles_base: Path | None = None,
    working_dir: Path | None = None,
) -> Credentials:
    """Resolve credentials by precedence: profile > env > .env > config.json.

    `profiles_base` and `working_dir` are injection points for testability.
    """
    working_dir = working_dir or Path.cwd()
    chosen_profile = profile or os.environ.get("AA_PROFILE")

    if chosen_profile:
        creds = _from_profile(chosen_profile, profiles_base)
        creds.validate()
        return creds

    env_creds = _from_env()
    if _is_complete(env_creds):
        env_creds.validate()
        return env_creds

    dotenv_creds = _from_dotenv(working_dir)
    if dotenv_creds and _is_complete(dotenv_creds):
        dotenv_creds.validate()
        return dotenv_creds

    cfg_creds = _from_config_json(working_dir)
    if cfg_creds and _is_complete(cfg_creds):
        cfg_creds.validate()
        return cfg_creds

    raise ConfigError(
        "No credentials found. Set ORG_ID/CLIENT_ID/SECRET/SCOPES env vars, "
        "create a profile (--profile-add), or place a config.json in the working directory."
    )


@dataclass(frozen=True, slots=True)
class ResolutionEntry:
    """One step in the credential resolution chain — used by --config-status."""

    priority: int  # 1 (highest) → N (lowest)
    source: str  # human label
    matched: bool  # True if this source produced the resolved value


def validate_only(*, profile: str | None = None, working_dir: Path | None = None) -> Credentials:
    """Resolve credentials and validate shape WITHOUT calling Adobe.

    Raises ConfigError for missing fields or malformed `org_id`."""
    creds = resolve(profile=profile, working_dir=working_dir)  # raises ConfigError on missing fields
    if not creds.org_id.endswith("@AdobeOrg"):
        raise ConfigError(
            f"org_id '{creds.org_id}' does not match Adobe shape (expected `<id>@AdobeOrg`)",
        )
    return creds


def resolution_chain(
    *,
    profile: str | None = None,
    profiles_base: Path | None = None,
    working_dir: Path | None = None,
) -> list[ResolutionEntry]:
    """Walk every credential source in priority order; report which matched.

    Order (highest precedence first, mirroring `resolve()`):
      1. --profile=<name>   (when `profile` is non-None and ~/.aa/orgs/<name>/config.json exists)
      2. env vars           (ORG_ID + CLIENT_ID + SECRET + SCOPES all present)
      3. .env (cwd)         (when python-dotenv is installed AND .env exists in cwd AND fills the four vars)
      4. config.json (cwd)  (when ./config.json exists and fills the four fields)

    The first source that fully populates the four required fields wins.
    Subsequent entries are reported with `matched=False`."""
    working_dir = working_dir or Path.cwd()
    chosen_profile = profile or os.environ.get("AA_PROFILE")
    entries: list[ResolutionEntry] = []
    matched_yet = False

    # 1. profile
    if chosen_profile:
        from aa_auto_sdr.core import profiles as profiles_mod

        path = (profiles_base or profiles_mod.default_base()) / "orgs" / chosen_profile / "config.json"
        ok = path.exists() and not matched_yet
        entries.append(ResolutionEntry(priority=1, source=f"--profile={chosen_profile}", matched=ok))
        matched_yet = matched_yet or ok
    else:
        entries.append(ResolutionEntry(priority=1, source="--profile (not set)", matched=False))

    # 2. env vars
    env_complete = all(os.environ.get(v) for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES"))
    env_ok = not matched_yet and env_complete
    entries.append(ResolutionEntry(priority=2, source="env vars", matched=env_ok))
    matched_yet = matched_yet or env_ok

    # 3. dotenv file in cwd
    dotenv_path = working_dir / ".env"
    dotenv_creds = _from_dotenv(working_dir) if dotenv_path.exists() else None
    dotenv_ok = not matched_yet and dotenv_creds is not None and _is_complete(dotenv_creds)
    entries.append(ResolutionEntry(priority=3, source=".env (cwd)", matched=dotenv_ok))
    matched_yet = matched_yet or dotenv_ok

    # 4. config.json (cwd)
    cfg_path = working_dir / "config.json"
    cfg_creds = _from_config_json(working_dir) if cfg_path.exists() else None
    cfg_ok = not matched_yet and cfg_creds is not None and _is_complete(cfg_creds)
    entries.append(ResolutionEntry(priority=4, source="config.json (cwd)", matched=cfg_ok))

    return entries
