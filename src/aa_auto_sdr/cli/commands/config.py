"""--profile-add and --show-config handlers."""

from __future__ import annotations

from pathlib import Path

from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode


def profile_add(name: str, *, base: Path | None = None) -> int:
    """Interactively prompt for credential fields and write them to a profile."""
    print(f"Creating profile '{name}'. Press Ctrl+C to cancel.")
    org_id = input("ORG_ID (e.g. abc@AdobeOrg): ").strip()
    client_id = input("CLIENT_ID: ").strip()
    secret = input("SECRET: ").strip()
    scopes = input("SCOPES: ").strip()
    sandbox = input("SANDBOX (optional, press enter to skip): ").strip()

    data = {
        "org_id": org_id,
        "client_id": client_id,
        "secret": secret,
        "scopes": scopes,
        "sandbox": sandbox or None,
    }
    path = profiles.write_profile(name, data, base=base)
    print(f"profile written: {path}")
    return ExitCode.OK.value


def show_config(*, profile: str | None, profiles_base: Path | None = None) -> int:
    """Print which credential source resolves first, without exposing secrets."""
    try:
        creds = credentials.resolve(profile=profile, profiles_base=profiles_base)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return ExitCode.CONFIG.value

    print(f"source:    {creds.source}")
    print(f"org_id:    {creds.org_id}")
    print(f"client_id: {creds.client_id[:4]}…{creds.client_id[-4:] if len(creds.client_id) > 8 else ''}")
    print(f"sandbox:   {creds.sandbox or '(none)'}")
    return ExitCode.OK.value
