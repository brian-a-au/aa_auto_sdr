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
from aa_auto_sdr.sdr.builder import build_sdr

_EXIT_OK = 0
_EXIT_GENERIC = 1
_EXIT_CONFIG = 10
_EXIT_AUTH = 11
_EXIT_API = 12
_EXIT_NOT_FOUND = 13
_EXIT_OUTPUT = 15


def run(*, rsid: str, output_dir: Path, format_name: str, profile: str | None) -> int:
    is_pipe = output_dir == Path("-")

    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_CONFIG

    if not is_pipe:
        print(f"using credentials from: {creds.source}")

    try:
        formats = registry.resolve_formats(format_name)
    except KeyError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_GENERIC

    if is_pipe and (len(formats) != 1 or formats[0] != "json"):
        print(
            f"error: format {format_name!r} cannot be piped to stdout; use --output-dir <DIR> instead",
            flush=True,
        )
        return _EXIT_OUTPUT

    # Vestigial pre-flight (every concrete format has a writer in v0.2+)
    registry.bootstrap()
    for fmt in formats:
        try:
            registry.get_writer(fmt)
        except KeyError:
            print(
                f"error: format '{fmt}' is not available in this build",
                flush=True,
            )
            return _EXIT_OUTPUT

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return _EXIT_AUTH

    try:
        canonical_rsids, was_name_lookup = fetch.resolve_rsid(client, rsid)
    except ReportSuiteNotFoundError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_NOT_FOUND
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API

    if not is_pipe:
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

    if is_pipe:
        # JSON-only pipe path: build SdrDocuments and emit one JSON value
        # (single object for one RSID, array of objects for multi-match).
        docs: list[dict] = []
        for canonical_rsid in canonical_rsids:
            try:
                doc = build_sdr(
                    client,
                    canonical_rsid,
                    captured_at=captured_at,
                    tool_version=__version__,
                )
            except ReportSuiteNotFoundError as e:
                print(f"error: {e}", flush=True)
                return _EXIT_NOT_FOUND
            except ApiError as e:
                print(f"api error: {e}", flush=True)
                return _EXIT_API
            docs.append(doc.to_dict())

        import json as _json
        import sys as _sys

        payload = docs[0] if total == 1 else docs
        _sys.stdout.write(_json.dumps(payload, indent=2, default=str) + "\n")
        _sys.stdout.flush()
        return _EXIT_OK

    # File-output path: per-RSID pipeline.run_single
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
