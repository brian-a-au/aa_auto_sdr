"""--profile-list / --profile-test / --profile-show / --profile-import handlers."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.api.sign_in import NOT_RUN, StepResult, request_token
from aa_auto_sdr.core import credentials, notices, profiles
from aa_auto_sdr.core.exceptions import ApiError, AuthError, ConfigError, NoCompanyAccessError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.version import __version__
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
                file=sys.stderr,
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


LIVE_TEST_SCHEMA = "adobe-credentials/v1/live-test"


def _company_check(
    creds: credentials.Credentials, retry_policy: RetryPolicy | None
) -> tuple[StepResult, str | None, int, str]:
    """The second result of the live test: one call to Analytics for the company.

    Returns the result, the company ID, the exit code and the label of the
    old `FAIL [...]` line."""
    try:
        from aa_auto_sdr.api.client import AaClient

        client = AaClient.from_credentials(creds, retry_policy=retry_policy)
    except NoCompanyAccessError as exc:
        return StepResult(False, "no_product_access", str(exc)), None, ExitCode.AUTH.value, "auth"
    except AuthError as exc:
        return StepResult(False, "unreachable", str(exc)), None, ExitCode.AUTH.value, "auth"
    except ApiError as exc:
        # The bootstrap retries getCompanyId, so an exhausted budget arrives
        # here as TransientApiError rather than AuthError.
        return StepResult(False, "unreachable", str(exc)), None, ExitCode.API.value, "api"
    return StepResult(True), client.company_id, ExitCode.OK.value, ""


def _step_line(label: str, step: StepResult) -> str:
    if step.ok is None:
        return f"{label}: not run"
    if step.ok:
        return f"{label}: ok"
    return f"{label}: FAIL [{step.code}] {step.message}"


def test_run(
    name: str,
    *,
    base: Path | None = None,  # noqa: PT028 — not a pytest test, naming collision is unavoidable
    retry_policy: RetryPolicy | None = None,  # noqa: PT028
    format_name: str | None = None,  # noqa: PT028
) -> int:
    """Test a profile against Adobe and report two results.

    The first result is sign-in: one token request to Adobe's sign-in service.
    The second is the company check: an OAuth + getCompanyId() round trip
    through the SDK. It runs only when sign-in worked. The report is this
    command's result, so it goes to stdout. `format_name="json"` prints it as
    JSON in the shape every Adobe tool shares."""
    started_ms = time.monotonic()
    logger.info("command_start command=profile_test", extra={"command": "profile_test"})
    exit_code = ExitCode.GENERIC.value
    try:
        as_json = format_name == "json"
        sign_in_result, company, company_id = NOT_RUN, NOT_RUN, None
        label, failure, problem_code = "", "", ""
        try:
            creds = credentials.resolve(profile=name, profiles_base=base)
        except ConfigError as exc:
            exit_code, label, failure = ExitCode.CONFIG.value, "config", str(exc)
            problem_code = exc.code or "no_credential"
        else:
            sign_in_result = request_token(creds)
            if sign_in_result.ok:
                company, company_id, exit_code, label = _company_check(creds, retry_policy)
                failure = company.message or ""
            else:
                # No answer at all is a network problem, like the same failure in the company check.
                exit_code = ExitCode.API.value if sign_in_result.no_answer else ExitCode.AUTH.value
                label = "api" if sign_in_result.no_answer else "auth"
                failure = sign_in_result.message or ""
        passed = exit_code == ExitCode.OK.value
        if as_json:
            payload = {
                "schema": LIVE_TEST_SCHEMA,
                "tool": "aa_auto_sdr",
                "tool_version": __version__,
                "product": "aa",
                "ok": passed,
                "source": {"kind": "flag_profile", "name": f"profile {name}"},
                "profile": name,
                "sign_in": sign_in_result.as_dict(),
                "product_access": company.as_dict(),
                "company_id": company_id,
            }
            if label == "config":
                payload["problems"] = [{"code": problem_code, "message": failure}]
            print(json.dumps(payload, indent=2), flush=True)
            return exit_code
        if label != "config":
            print(_step_line("sign-in", sign_in_result))
            print(_step_line("company check", company))
        if passed:
            print(f"PASS: profile '{name}' authenticated; company_id={company_id}")
        else:
            print(f"FAIL [{label}]: {failure}", flush=True)
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
            print(f"error: {exc}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        snap_dir = (base or profiles.default_base()) / "orgs" / name / "snapshots"
        snap_count = len(list_snapshots(snap_dir))
        # str(): a hand-written config.json can hold null or a number here.
        cid = "" if data.get("client_id") is None else str(data["client_id"])
        masked = credentials.mask_client_id(cid) if cid else ""
        path = profiles.profile_config_path(name, base=base)
        if profiles.readable_by_others(path):
            notices.say(
                "warning",
                f"{path} holds a credential and other users of this computer can read it. "
                f'To fix this, run: chmod 600 "{path}"',
            )
        print(f"profile:    {name}")
        print(f"org_id:     {data.get('org_id', '')}")
        print(f"client_id:  {masked}")
        print(f"secret:     {credentials.mask_secret('' if data.get('secret') is None else str(data['secret']))}")
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
        try:
            profiles.check_profile_name(name, base=base)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        src = Path(file_path).expanduser()
        if not os.path.exists(src):
            print(f"error: file not found: {src}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        try:
            with src.open(encoding="utf-8-sig") as fh:  # accepts a PowerShell 5 BOM
                data = json.load(fh)
        except (ValueError, OSError) as exc:  # ValueError covers JSONDecodeError and UnicodeDecodeError
            print(f"error: could not read {src}: {exc}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        if not isinstance(data, dict):
            print(f"error: {src} must hold a JSON object, got {type(data).__name__}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code
        required = {"org_id", "client_id", "secret", "scopes"}
        missing = required - data.keys()
        if missing:
            print(f"error: missing required fields: {sorted(missing)}", flush=True, file=sys.stderr)
            exit_code = ExitCode.CONFIG.value
            return exit_code

        target_dir = (base or profiles.default_base()) / "orgs" / name
        # A snapshot run with no --profile creates orgs/default/snapshots/
        # alone; that folder is not a profile. So a directory with no
        # config.json entry (lexists: a dangling link still counts) is free.
        # A file at the target is still refused. The name check above has
        # already refused names that resolve outside one folder under orgs/.
        snapshot_only_dir = os.path.isdir(target_dir) and not os.path.lexists(target_dir / "config.json")
        if os.path.lexists(target_dir) and not snapshot_only_dir and not overwrite:
            print(
                f"error: profile '{name}' already exists at {target_dir}. Pass --profile-overwrite to replace.",
                flush=True,
                file=sys.stderr,
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
