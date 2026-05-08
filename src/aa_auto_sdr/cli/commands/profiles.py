"""--profile-list / --profile-test / --profile-show / --profile-import handlers."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import AuthError, ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.snapshot.store import list_snapshots

logger = logging.getLogger(__name__)


def list_run(
    *,
    format_name: str | None = None,
    base: Path | None = None,
) -> int:
    """List profile names. Format: table (default) or json."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_list", extra={"command": "profile_list"})
    exit_code = ExitCode.GENERIC.value
    try:
        names = profiles.list_profiles(base=base)
        fmt = format_name or "table"
        if fmt == "json":
            print(json.dumps(names, sort_keys=True, indent=2))
        elif fmt == "table":
            if not names:
                print("(no profiles)")
            else:
                print("PROFILE")
                for n in names:
                    print(f"  {n}")
        else:
            print(
                f"error: --profile-list format must be json|table (got '{fmt}')",
                flush=True,
            )
            exit_code = ExitCode.OUTPUT.value
            return exit_code
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=profile_list exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "profile_list",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def test_run(
    name: str,
    *,
    base: Path | None = None,  # noqa: PT028 — not a pytest test, naming collision is unavoidable
    retry_policy: RetryPolicy | None = None,  # noqa: PT028
) -> int:
    """Resolve creds and perform a real OAuth + getCompanyId() round trip."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_test", extra={"command": "profile_test"})
    exit_code = ExitCode.GENERIC.value
    try:
        try:
            creds = credentials.resolve(profile=name, profiles_base=base)
        except ConfigError as exc:
            print(f"FAIL [config]: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        try:
            from aa_auto_sdr.api.client import AaClient

            client = AaClient.from_credentials(creds, retry_policy=retry_policy)
        except AuthError as exc:
            print(f"FAIL [auth]: {exc}", flush=True)
            exit_code = ExitCode.AUTH.value
            return exit_code
        print(f"PASS: profile '{name}' authenticated; company_id={client.company_id}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=profile_test exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "profile_test",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def show_run(name: str, *, base: Path | None = None) -> int:
    """Print profile fields with masked client_id and no secret."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_show", extra={"command": "profile_show"})
    exit_code = ExitCode.GENERIC.value
    try:
        try:
            data = profiles.read_profile(name, base=base)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        snap_dir = (base or profiles.default_base()) / "orgs" / name / "snapshots"
        snap_count = len(list_snapshots(snap_dir))
        cid = data.get("client_id", "")
        masked = f"{cid[:4]}…{cid[-4:]}" if len(cid) > 8 else cid
        print(f"profile:    {name}")
        print(f"org_id:     {data.get('org_id', '')}")
        print(f"client_id:  {masked}")
        print(f"scopes:     {data.get('scopes', '')}")
        print(f"snapshots:  {snap_count}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=profile_show exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "profile_show",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )


def import_run(
    name: str,
    file_path: str,
    *,
    base: Path | None = None,
    overwrite: bool = False,
) -> int:
    """Read a JSON file and write it as a profile. Validates required fields.

    By default, errors if the profile already exists at `~/.aa/orgs/<name>/`.
    Pass `overwrite=True` (CLI: `--profile-overwrite`) to replace an existing
    profile. v1.1 silently overwrote; v1.2 makes the replacement explicit."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_import", extra={"command": "profile_import"})
    exit_code = ExitCode.GENERIC.value
    try:
        src = Path(file_path).expanduser()
        if not src.exists():
            print(f"error: file not found: {src}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        try:
            with src.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"error: could not read {src}: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        required = {"org_id", "client_id", "secret", "scopes"}
        missing = required - data.keys()
        if missing:
            print(f"error: missing required fields: {sorted(missing)}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code

        target_dir = (base or profiles.default_base()) / "orgs" / name
        if target_dir.exists() and not overwrite:
            print(
                f"error: profile '{name}' already exists at {target_dir}. Pass --profile-overwrite to replace.",
                flush=True,
            )
            exit_code = ExitCode.CONFIG.value
            return exit_code

        path = profiles.write_profile(name, data, base=base)
        print(f"profile imported: {path}")
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=profile_import exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "profile_import",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )
