"""--profile-add and --show-config handlers."""

from __future__ import annotations

import json
import sys
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


def sample_config() -> int:
    """Emit a config.json template to stdout."""
    template = {
        "org_id": "<org-id>@AdobeOrg",
        "client_id": "<client-id>",
        "secret": "<client-secret>",
        "scopes": "openid AdobeID additional_info.projectedProductContext",
        "sandbox": None,
    }
    sys.stdout.write(json.dumps(template, sort_keys=True, indent=2) + "\n")
    return ExitCode.OK.value


def validate_config(*, profile: str | None) -> int:
    """Resolve credentials and validate shape WITHOUT calling Adobe."""
    try:
        credentials.validate_only(profile=profile)
    except ConfigError as exc:
        print(f"error: {exc}", flush=True)
        return ExitCode.CONFIG.value
    print("config valid (shape only — no API call made)")
    return ExitCode.OK.value


def config_status(*, profile: str | None) -> int:
    """Print full credential resolution chain — every source checked, which won."""
    chain = credentials.resolution_chain(profile=profile)
    print("Resolution chain (highest precedence first):")
    for entry in chain:
        marker = "✓" if entry.matched else "⊘"
        note = "MATCHED" if entry.matched else "skipped"
        print(f"  {entry.priority}. {entry.source:<28}  {marker} {note}")
    print()
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as exc:
        print(f"resolution failed: {exc}", flush=True)
        return ExitCode.CONFIG.value
    print("Resolved values (sensitive fields masked):")
    cid = creds.client_id
    masked = f"{cid[:4]}…{cid[-4:]}" if len(cid) > 8 else cid
    print(f"  org_id:    {creds.org_id}")
    print(f"  client_id: {masked}")
    print(f"  scopes:    {creds.scopes}")
    print(f"  sandbox:   {creds.sandbox or '(none)'}")
    return ExitCode.OK.value
