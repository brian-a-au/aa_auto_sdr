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
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.version import __version__
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.sdr.builder import build_sdr


def _emit_pipe_or_print(
    *,
    is_pipe: bool,
    exc: BaseException | None,
    message: str,
    exit_code: int,
) -> None:
    """Pipe-aware error emitter. On pipe path, write JSON envelope to stderr;
    otherwise print human-readable message to stdout. Master spec §6.2: pipe-path
    failures must keep stdout silent so downstream `jq` etc. sees empty input."""
    if is_pipe:
        from aa_auto_sdr.output.error_envelope import emit_error_envelope

        # Synthesize an exception when only a string message is available
        # (e.g. format-rejection paths that don't have an exception object).
        emit_error_envelope(exc if exc is not None else RuntimeError(message), exit_code)
    else:
        print(message, flush=True)


def run(
    *,
    rsid: str,
    output_dir: Path,
    format_name: str,
    profile: str | None,
    snapshot: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    keep_last: int | None = None,
    keep_since: str | None = None,
    metrics_only: bool = False,  # v1.2
    dimensions_only: bool = False,  # v1.2
    dry_run: bool = False,  # v1.2 — preview-only; no component fetch, no writes
) -> int:
    is_pipe = output_dir == Path("-")

    if metrics_only and dimensions_only:
        msg = "error: --metrics-only and --dimensions-only are mutually exclusive"
        _emit_pipe_or_print(
            is_pipe=is_pipe,
            exc=None,
            message=msg,
            exit_code=ExitCode.USAGE.value,
        )
        return ExitCode.USAGE.value

    from aa_auto_sdr.sdr.builder import ComponentFilter

    component_filter = ComponentFilter.from_args(
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
    )

    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        _emit_pipe_or_print(is_pipe=is_pipe, exc=e, message=f"error: {e}", exit_code=ExitCode.CONFIG.value)
        return ExitCode.CONFIG.value

    snapshot_dir: Path | None = None
    save_required = snapshot or auto_snapshot
    if save_required:
        if not profile:
            flag = "--snapshot" if snapshot else "--auto-snapshot"
            msg = f"error: {flag} requires --profile (snapshots are profile-scoped)"
            _emit_pipe_or_print(is_pipe=is_pipe, exc=None, message=msg, exit_code=ExitCode.CONFIG.value)
            return ExitCode.CONFIG.value
        from aa_auto_sdr.core.profiles import default_base

        snapshot_dir = default_base() / "orgs" / profile / "snapshots"

    if not is_pipe:
        print(f"using credentials from: {creds.source}")

    try:
        formats = registry.resolve_formats(format_name)
    except KeyError as e:
        _emit_pipe_or_print(is_pipe=is_pipe, exc=e, message=f"error: {e}", exit_code=ExitCode.GENERIC.value)
        return ExitCode.GENERIC.value

    if is_pipe and (len(formats) != 1 or formats[0] != "json"):
        msg = f"error: format {format_name!r} cannot be piped to stdout; use --output-dir <DIR> instead"
        _emit_pipe_or_print(is_pipe=is_pipe, exc=None, message=msg, exit_code=ExitCode.OUTPUT.value)
        return ExitCode.OUTPUT.value

    # Vestigial pre-flight (every concrete format has a writer in v0.2+)
    registry.bootstrap()
    for fmt in formats:
        try:
            registry.get_writer(fmt)
        except KeyError:
            msg = f"error: format '{fmt}' is not available in this build"
            _emit_pipe_or_print(is_pipe=is_pipe, exc=None, message=msg, exit_code=ExitCode.OUTPUT.value)
            return ExitCode.OUTPUT.value

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        _emit_pipe_or_print(is_pipe=is_pipe, exc=e, message=f"auth error: {e}", exit_code=ExitCode.AUTH.value)
        return ExitCode.AUTH.value

    try:
        canonical_rsids, was_name_lookup = fetch.resolve_rsid(client, rsid)
    except ReportSuiteNotFoundError as e:
        _emit_pipe_or_print(is_pipe=is_pipe, exc=e, message=f"error: {e}", exit_code=ExitCode.NOT_FOUND.value)
        return ExitCode.NOT_FOUND.value
    except ApiError as e:
        _emit_pipe_or_print(is_pipe=is_pipe, exc=e, message=f"api error: {e}", exit_code=ExitCode.API.value)
        return ExitCode.API.value

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

    if dry_run:
        # Preview-only path (v1.2): credentials resolved + auth round-trip done +
        # RSID resolved → list what would be written and exit. No component
        # fetches (the heavy AA calls), no file writes, no snapshot writes.
        print("DRY RUN — would generate:", flush=True)
        ext_map = {
            "excel": "xlsx",
            "json": "json",
            "html": "html",
            "markdown": "md",
            "csv": "csv",
        }
        for canonical_rsid in canonical_rsids:
            for fmt in formats:
                if fmt == "csv":
                    # CSV mode produces one file per component type.
                    print(f"  {output_dir / f'{canonical_rsid}.<component>.csv'}")
                else:
                    ext = ext_map.get(fmt, fmt)
                    print(f"  {output_dir / f'{canonical_rsid}.{ext}'}")
            if save_required and snapshot_dir is not None:
                from aa_auto_sdr.snapshot.store import snapshot_path

                snap_path = snapshot_path(
                    snapshot_dir=snapshot_dir,
                    rsid=canonical_rsid,
                    captured_at_iso=captured_at.isoformat(),
                )
                print(f"  {snap_path}")
        print("(no files were written; remove --dry-run to execute)", flush=True)
        return ExitCode.OK.value

    if is_pipe:
        # JSON-only pipe path: build SdrDocuments and emit one JSON value
        # (single object for one RSID, array of objects for multi-match).
        docs: list[dict] = []
        from aa_auto_sdr.output.error_envelope import emit_error_envelope

        for canonical_rsid in canonical_rsids:
            try:
                doc = build_sdr(
                    client,
                    canonical_rsid,
                    captured_at=captured_at,
                    tool_version=__version__,
                    component_filter=component_filter,
                )
            except ReportSuiteNotFoundError as e:
                emit_error_envelope(e, ExitCode.NOT_FOUND.value)
                return ExitCode.NOT_FOUND.value
            except ApiError as e:
                emit_error_envelope(e, ExitCode.API.value)
                return ExitCode.API.value
            docs.append(doc.to_dict())
            if snapshot_dir is not None:
                from aa_auto_sdr.snapshot.store import save_snapshot

                save_snapshot(doc, snapshot_dir=snapshot_dir)

        import json as _json
        import sys as _sys

        payload = docs[0] if total == 1 else docs
        _sys.stdout.write(_json.dumps(payload, indent=2, default=str) + "\n")
        _sys.stdout.flush()

        if auto_prune and snapshot_dir is not None:
            rc = _apply_auto_prune(
                is_pipe=is_pipe,
                snapshot_dir=snapshot_dir,
                rsids=canonical_rsids,
                keep_last=keep_last,
                keep_since=keep_since,
            )
            if rc != ExitCode.OK.value:
                return rc
        return ExitCode.OK.value

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
                snapshot_dir=snapshot_dir,
                component_filter=component_filter,
            )
        except ReportSuiteNotFoundError as e:
            print(f"error: {e}", flush=True)
            return ExitCode.NOT_FOUND.value
        except ApiError as e:
            print(f"api error: {e}", flush=True)
            return ExitCode.API.value
        except OutputError as e:
            print(f"output error: {e}", flush=True)
            return ExitCode.OUTPUT.value
        except AaAutoSdrError as e:
            print(f"error: {e}", flush=True)
            return ExitCode.GENERIC.value

        for path in result.outputs:
            print(f"wrote: {path}")

    if auto_prune and snapshot_dir is not None:
        rc = _apply_auto_prune(
            is_pipe=is_pipe,
            snapshot_dir=snapshot_dir,
            rsids=canonical_rsids,
            keep_last=keep_last,
            keep_since=keep_since,
        )
        if rc != ExitCode.OK.value:
            return rc

    return ExitCode.OK.value


def _apply_auto_prune(
    *,
    is_pipe: bool,
    snapshot_dir: Path,
    rsids: list[str],
    keep_last: int | None,
    keep_since: str | None,
) -> int:
    """Parse retention policy and prune each RSID under `snapshot_dir`.

    Returns ExitCode.OK on success, ExitCode.CONFIG on bad/empty policy.
    """
    from aa_auto_sdr.snapshot.retention import parse_policy
    from aa_auto_sdr.snapshot.store import prune_snapshots

    try:
        policy = parse_policy(keep_last=keep_last, keep_since=keep_since)
    except ConfigError as exc:
        msg = f"error: {exc}"
        _emit_pipe_or_print(is_pipe=is_pipe, exc=exc, message=msg, exit_code=ExitCode.CONFIG.value)
        return ExitCode.CONFIG.value
    if not policy.is_active():
        msg = "error: --auto-prune requires --keep-last or --keep-since"
        _emit_pipe_or_print(is_pipe=is_pipe, exc=None, message=msg, exit_code=ExitCode.CONFIG.value)
        return ExitCode.CONFIG.value
    for rs in rsids:
        prune_snapshots(snapshot_dir, policy, rsid=rs)
    return ExitCode.OK.value
