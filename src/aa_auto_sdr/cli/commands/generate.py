"""generate command: resolve creds → build client → run single pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    AaAutoSdrError,
    ApiError,
    AuthError,
    ConfigError,
    OutputError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.version import __version__
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline import single

_EXIT_OK = 0
_EXIT_GENERIC = 1
_EXIT_CONFIG = 10
_EXIT_AUTH = 11
_EXIT_API = 12
_EXIT_NOT_FOUND = 13
_EXIT_OUTPUT = 15


def run(*, rsid: str, output_dir: Path, format_name: str, profile: str | None) -> int:
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_CONFIG

    print(f"using credentials from: {creds.source}")

    try:
        formats = registry.resolve_formats(format_name)
    except KeyError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_GENERIC

    # In v0.1 only `json` and `excel` writers are registered. Surface a clean
    # error if a user requests a format whose writer is not in this build.
    registry.bootstrap()
    for fmt in formats:
        try:
            registry.get_writer(fmt)
        except KeyError:
            print(
                f"error: format '{fmt}' is not available in this build (v0.1 ships excel + json)",
                flush=True,
            )
            return _EXIT_OUTPUT

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return _EXIT_AUTH

    # Resolve <RSID-or-name> to one or more canonical RSIDs.
    try:
        canonical_rsids, was_name_lookup = fetch.resolve_rsid(client, rsid)
    except ReportSuiteNotFoundError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_NOT_FOUND
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API

    if was_name_lookup and len(canonical_rsids) > 1:
        print(
            f"{rsid!r} matches {len(canonical_rsids)} report suites: {', '.join(canonical_rsids)}",
        )
    elif was_name_lookup:
        print(f"using report suite: {rsid!r} (rsid: {canonical_rsids[0]})")
    else:
        print(f"using report suite: {canonical_rsids[0]}")

    captured_at = datetime.now(UTC)
    total = len(canonical_rsids)

    for index, canonical_rsid in enumerate(canonical_rsids, start=1):
        if total > 1:
            print(f"generating SDR {index}/{total}: {canonical_rsid}")
        try:
            result = single.run_single(
                client=client,
                rsid=canonical_rsid,
                formats=formats,
                output_dir=output_dir,
                captured_at=captured_at,
                tool_version=__version__,
            )
        except ReportSuiteNotFoundError as e:
            print(f"error: {e}", flush=True)
            return _EXIT_NOT_FOUND
        except ApiError as e:
            print(f"api error: {e}", flush=True)
            return _EXIT_API
        except OutputError as e:
            print(f"output error: {e}", flush=True)
            return _EXIT_OUTPUT
        except AaAutoSdrError as e:
            print(f"error: {e}", flush=True)
            return _EXIT_GENERIC

        for path in result.outputs:
            print(f"wrote: {path}")

    return _EXIT_OK
