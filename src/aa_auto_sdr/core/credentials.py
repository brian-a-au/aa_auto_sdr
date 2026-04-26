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
    sandbox: str | None
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
        sandbox=(str(d["sandbox"]).strip() or None) if d.get("sandbox") else None,
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
            "sandbox": os.environ.get("SANDBOX"),
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
