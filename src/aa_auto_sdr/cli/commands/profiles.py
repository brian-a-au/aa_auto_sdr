"""--profile-list / --profile-test / --profile-show / --profile-import handlers."""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import AuthError, ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.snapshot.store import list_snapshots


def list_run(
    *,
    format_name: str | None = None,
    base: Path | None = None,
) -> int:
    """List profile names. Format: table (default) or json."""
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
        return ExitCode.OUTPUT.value
    return ExitCode.OK.value


def test_run(name: str, *, base: Path | None = None) -> int:  # noqa: PT028
    """Resolve creds and perform a real OAuth + getCompanyId() round trip."""
    try:
        creds = credentials.resolve(profile=name, profiles_base=base)
    except ConfigError as exc:
        print(f"FAIL [config]: {exc}", flush=True)
        return ExitCode.CONFIG.value
    try:
        from aa_auto_sdr.api.client import AaClient

        client = AaClient.from_credentials(creds)
    except AuthError as exc:
        print(f"FAIL [auth]: {exc}", flush=True)
        return ExitCode.AUTH.value
    print(f"PASS: profile '{name}' authenticated; company_id={client.company_id}")
    return ExitCode.OK.value


def show_run(name: str, *, base: Path | None = None) -> int:
    """Print profile fields with masked client_id and no secret."""
    try:
        data = profiles.read_profile(name, base=base)
    except ConfigError as exc:
        print(f"error: {exc}", flush=True)
        return ExitCode.CONFIG.value
    snap_dir = (base or profiles.default_base()) / "orgs" / name / "snapshots"
    snap_count = len(list_snapshots(snap_dir))
    cid = data.get("client_id", "")
    masked = f"{cid[:4]}…{cid[-4:]}" if len(cid) > 8 else cid
    print(f"profile:    {name}")
    print(f"org_id:     {data.get('org_id', '')}")
    print(f"client_id:  {masked}")
    print(f"scopes:     {data.get('scopes', '')}")
    print(f"sandbox:    {data.get('sandbox') or '(none)'}")
    print(f"snapshots:  {snap_count}")
    return ExitCode.OK.value


def import_run(name: str, file_path: str, *, base: Path | None = None) -> int:
    """Read a JSON file and write it as a profile. Validates required fields."""
    src = Path(file_path).expanduser()
    if not src.exists():
        print(f"error: file not found: {src}", flush=True)
        return ExitCode.CONFIG.value
    try:
        with src.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"error: could not read {src}: {exc}", flush=True)
        return ExitCode.CONFIG.value
    required = {"org_id", "client_id", "secret", "scopes"}
    missing = required - data.keys()
    if missing:
        print(f"error: missing required fields: {sorted(missing)}", flush=True)
        return ExitCode.CONFIG.value
    path = profiles.write_profile(name, data, base=base)
    print(f"profile imported: {path}")
    return ExitCode.OK.value
