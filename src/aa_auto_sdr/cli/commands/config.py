"""--profile-add and --show-config handlers."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode

logger = logging.getLogger(__name__)


def profile_add(name: str, *, base: Path | None = None) -> int:
    """Interactively prompt for credential fields and write them to a profile."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_add", extra={"command": "profile_add"})
    exit_code = ExitCode.GENERIC.value
    try:
        print(f"Creating profile '{name}'. Press Ctrl+C to cancel.")
        org_id = input("ORG_ID (e.g. abc@AdobeOrg): ").strip()
        client_id = input("CLIENT_ID: ").strip()
        secret = input("SECRET: ").strip()
        scopes = input("SCOPES: ").strip()

        data = {
            "org_id": org_id,
            "client_id": client_id,
            "secret": secret,
            "scopes": scopes,
        }
        path = profiles.write_profile(name, data, base=base)
        print(f"profile written: {path}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=profile_add exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "profile_add",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def show_config(*, profile: str | None, profiles_base: Path | None = None) -> int:
    """Print which credential source resolves first, without exposing secrets."""
    started_ms = time.monotonic()
    logger.info("command_start command=show_config", extra={"command": "show_config"})
    exit_code = ExitCode.GENERIC.value
    try:
        try:
            creds = credentials.resolve(profile=profile, profiles_base=profiles_base)
        except ConfigError as e:
            print(f"error: {e}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code

        print(f"source:    {creds.source}")
        print(f"org_id:    {creds.org_id}")
        print(f"client_id: {creds.client_id[:4]}…{creds.client_id[-4:] if len(creds.client_id) > 8 else ''}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=show_config exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "show_config",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def sample_config() -> int:
    """Emit a config.json template to stdout."""
    started_ms = time.monotonic()
    logger.info("command_start command=sample_config", extra={"command": "sample_config"})
    exit_code = ExitCode.GENERIC.value
    try:
        template = {
            "org_id": "<org-id>@AdobeOrg",
            "client_id": "<client-id>",
            "secret": "<client-secret>",
            "scopes": "openid,AdobeID,additional_info.projectedProductContext",
        }
        sys.stdout.write(json.dumps(template, sort_keys=True, indent=2) + "\n")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=sample_config exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "sample_config",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def validate_config(*, profile: str | None) -> int:
    """Resolve credentials and validate shape WITHOUT calling Adobe."""
    started_ms = time.monotonic()
    logger.info("command_start command=validate_config", extra={"command": "validate_config"})
    exit_code = ExitCode.GENERIC.value
    try:
        try:
            credentials.validate_only(profile=profile)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        print("config valid (shape only — no API call made)")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=validate_config exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "validate_config",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def config_status(*, profile: str | None) -> int:
    """Print full credential resolution chain — every source checked, which won."""
    started_ms = time.monotonic()
    logger.info("command_start command=config_status", extra={"command": "config_status"})
    exit_code = ExitCode.GENERIC.value
    try:
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
            exit_code = ExitCode.CONFIG.value
            return exit_code
        print("Resolved values (sensitive fields masked):")
        cid = creds.client_id
        masked = f"{cid[:4]}…{cid[-4:]}" if len(cid) > 8 else cid
        print(f"  org_id:    {creds.org_id}")
        print(f"  client_id: {masked}")
        print(f"  scopes:    {creds.scopes}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=config_status exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "config_status",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )
