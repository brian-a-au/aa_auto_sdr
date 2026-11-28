"""--profile-add and --show-config handlers."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.version import __version__

logger = logging.getLogger(__name__)


def profile_add(name: str, *, base: Path | None = None) -> int:
    """Interactively prompt for credential fields and write them to a profile."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_add", extra={"command": "profile_add"})
    exit_code = ExitCode.GENERIC.value
    try:
        try:
            profiles.check_profile_name(name, base=base)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code

        print(f"Creating profile '{name}'. Press Ctrl+C to cancel.")
        fields = (
            ("org_id", "ORG_ID", "ORG_ID (e.g. abc@AdobeOrg): "),
            ("client_id", "CLIENT_ID", "CLIENT_ID: "),
            ("secret", "SECRET", "SECRET: "),
            ("scopes", "SCOPES", "SCOPES: "),
        )
        data: dict[str, str] = {}
        for key, label, prompt in fields:
            try:
                answer = input(prompt).strip()
            except KeyboardInterrupt:
                # End the prompt line on stdout (where input() wrote it) so the
                # one stderr line starts on a line of its own.
                print(flush=True)
                print("cancelled; profile not written", flush=True, file=sys.stderr)
                exit_code = 130  # shell SIGINT convention, as in --interactive
                return exit_code
            except EOFError:
                print(
                    f"\nerror: input ended before all four fields were entered; profile '{name}' not written",
                    flush=True,
                    file=sys.stderr,
                )
                exit_code = ExitCode.CONFIG.value
                return exit_code
            if not answer:
                print(f"error: {label} is empty; profile '{name}' not written", flush=True, file=sys.stderr)
                exit_code = ExitCode.CONFIG.value
                return exit_code
            data[key] = answer

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


CONFIG_CHECK_SCHEMA = "adobe-credentials/v1/config-check"
TOOL_NAME = "aa_auto_sdr"
PRODUCT = "aa"


def config_check_payload(found: credentials.Lookup) -> dict[str, Any]:
    """The config check as JSON, in the shape every Adobe tool shares.

    The secret is reported as `secret_set` only, and the client ID is masked."""
    creds = found.creds
    return {
        "schema": CONFIG_CHECK_SCHEMA,
        "tool": TOOL_NAME,
        "tool_version": __version__,
        "product": PRODUCT,
        "ok": creds is not None and not found.problems,
        "profile": found.profile,
        "sources": [source.as_dict() for source in found.sources],
        "credential": {
            "org_id": creds.org_id if creds else None,
            "client_id": credentials.mask_client_id(creds.client_id) if creds else None,
            "secret_set": bool(creds and creds.secret),
            "scopes": creds.scopes if creds else None,
        },
        "problems": [problem.as_dict() for problem in found.problems],
        "notices": [notice.as_dict() for notice in found.notices],
        "warnings": [warning.as_dict() for warning in found.warnings],
    }


def _print_config_check_json(found: credentials.Lookup) -> None:
    sys.stdout.write(json.dumps(config_check_payload(found), indent=2) + "\n")


def _source_label(used: credentials.SourceReport | None, source: str) -> str:
    """The winning source with its file path, e.g. `config.json (/work/config.json)`."""
    if used is None or not used.path or used.kind == "flag_config":  # a --config label already holds the path
        return source
    return f"{source} ({used.path})"


def _print_show_config(shown: credentials.ShownCredential) -> None:
    """The text output of --show-config. It gets no secret, only the fixed mask."""
    print(f"source:    {shown.source}")
    print(f"org_id:    {shown.org_id}")
    print(f"client_id: {shown.client_id}")
    # A resolved credential always has a secret, so the line is the fixed mask.
    print(f"secret:    {credentials.MASK}")
    print(f"scopes:    {shown.scopes}")


def _print_resolved_values(shown: credentials.ShownCredential, source_label: str) -> None:
    """The "Resolved values" block of --config-status. It gets no secret, only the fixed mask."""
    print("Resolved values (sensitive fields masked):")
    print(f"  source:    {source_label}")
    print(f"  org_id:    {shown.org_id}")
    print(f"  client_id: {shown.client_id}")
    print(f"  secret:    {credentials.MASK}")
    # Render scopes in the canonical no-space comma form (see docs/CONFIGURATION.md),
    # regardless of how they were entered.
    canonical_scopes = ",".join(s.strip() for s in shown.scopes.split(",") if s.strip())
    print(f"  scopes:    {canonical_scopes}")


def show_config(
    *,
    profile: str | None,
    profiles_base: Path | None = None,
    format_name: str | None = None,
) -> int:
    """Print which credential source resolves first, without exposing secrets.

    `format_name="json"` prints the config check as JSON instead."""
    started_ms = time.monotonic()
    logger.info("command_start command=show_config", extra={"command": "show_config"})
    exit_code = ExitCode.GENERIC.value
    try:
        as_json = format_name == "json"
        found = credentials.lookup(profile=profile, profiles_base=profiles_base, scan_all=as_json)
        found.announce()
        if as_json:
            _print_config_check_json(found)
        if found.creds is None:
            print(f"error: {found.error}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        if not as_json:
            _print_show_config(found.creds.shown())
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
            print(f"error: {exc}", flush=True, file=sys.stderr)
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


def config_status(*, profile: str | None, format_name: str | None = None) -> int:
    """Print full credential resolution chain — every source checked, which won.

    This is the config check. It makes no network call. `format_name="json"`
    prints it as JSON instead."""
    started_ms = time.monotonic()
    logger.info("command_start command=config_status", extra={"command": "config_status"})
    exit_code = ExitCode.GENERIC.value
    try:
        found = credentials.lookup(profile=profile, scan_all=True)
        found.announce()
        if format_name == "json":
            _print_config_check_json(found)
            if found.creds is None:
                print(f"resolution failed: {found.error}", flush=True, file=sys.stderr)
                exit_code = ExitCode.CONFIG.value
                return exit_code
            exit_code = ExitCode.OK.value
            return exit_code
        print("Resolution chain (highest precedence first):")
        for entry in credentials.chain_of(found, profile=profile):
            marker = "✓" if entry.matched else "⊘"
            note = "MATCHED" if entry.matched else "skipped"
            if entry.missing:
                note = f"skipped (partial, missing: {', '.join(entry.missing)})"
            print(f"  {entry.priority}. {entry.source:<28}  {marker} {note}")
        print()
        if found.creds is None:
            print(f"resolution failed: {found.error}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        shown = found.creds.shown()
        _print_resolved_values(shown, _source_label(found.used, shown.source))
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
