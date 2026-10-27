"""``--render-from TOKEN`` command handler.

Rebuilds an SdrDocument from saved SDR JSON (``--format json`` output) or a
snapshot envelope, then runs the normal writers. Fully offline: no
credentials, no client, no Adobe Analytics calls, and this module never
imports the SDK or the client.

I/O (resolving and reading the token, writing outputs) lives here; the
dict -> SdrDocument rebuild is the pure ``sdr.rebuild`` module.

Exit codes:
- SNAPSHOT (16): the token cannot be resolved or read (missing file,
  directory, invalid JSON, ``<RSID>@...`` without a snapshot dir, git
  failure), or a snapshot envelope is unsupported or malformed.
- GENERIC (1): the file is not a snapshot envelope and is not valid SDR
  JSON (unknown shape, bad rows, duplicate ids). Matches ``--push-to-notion``.
- OUTPUT (15): unknown ``--format``, a non-JSON format with ``--output -``,
  or a write failure.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.exceptions import SdrPayloadError, SnapshotError, SnapshotResolveError
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.version import __version__

logger = logging.getLogger(__name__)


def run(
    *,
    token: str,
    output_dir: Path,
    format_name: str,
    profile: str | None,
    snapshot_dir: Path | None,
    template_path: Path | None = None,
    template_organization: str | None = None,
) -> int:
    """Emit command_start/command_complete around the real body."""
    started_ms = time.monotonic()
    logger.info("command_start command=render_from", extra={"command": "render_from"})
    exit_code = ExitCode.GENERIC.value
    try:
        exit_code = _run_impl(
            token=token,
            output_dir=output_dir,
            format_name=format_name,
            profile=profile,
            snapshot_dir=snapshot_dir,
            template_path=template_path,
            template_organization=template_organization,
        )
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=render_from exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={"command": "render_from", "exit_code": exit_code, "duration_ms": duration_ms},
        )


def _fail(*, is_pipe: bool, exc: BaseException | None, message: str, exit_code: int) -> int:
    """Pipe path: JSON error envelope on stderr, stdout untouched. Otherwise a plain stderr line."""
    if is_pipe:
        from aa_auto_sdr.output.error_envelope import emit_error_envelope

        emit_error_envelope(exc if exc is not None else RuntimeError(message), exit_code)
    else:
        print(message, file=sys.stderr, flush=True)
    return exit_code


def _run_impl(
    *,
    token: str,
    output_dir: Path,
    format_name: str,
    profile: str | None,
    snapshot_dir: Path | None,
    template_path: Path | None,
    template_organization: str | None,
) -> int:
    from aa_auto_sdr.output import registry

    is_pipe = output_dir == Path("-")

    # Format checks come before any read so a bad flag fails fast.
    try:
        formats = registry.resolve_formats(format_name)
    except KeyError as exc:
        return _fail(is_pipe=is_pipe, exc=exc, message=f"error: {exc}", exit_code=ExitCode.OUTPUT.value)
    if template_path is not None:
        formats = registry.swap_excel_for_template(formats)
    if is_pipe and formats != ["json"]:
        msg = f"error: format {format_name!r} cannot be piped to stdout; use --output-dir <DIR> instead"
        return _fail(is_pipe=is_pipe, exc=None, message=msg, exit_code=ExitCode.OUTPUT.value)

    try:
        payload = _load_token(token, profile=profile, snapshot_dir=snapshot_dir)
    except SnapshotError as exc:
        return _fail(is_pipe=is_pipe, exc=exc, message=f"snapshot error: {exc}", exit_code=ExitCode.SNAPSHOT.value)

    from aa_auto_sdr.sdr.rebuild import document_from_payload

    try:
        doc = document_from_payload(payload, rendered_at=datetime.now(UTC), rendering_tool_version=__version__)
    except SnapshotError as exc:
        return _fail(is_pipe=is_pipe, exc=exc, message=f"snapshot error: {exc}", exit_code=ExitCode.SNAPSHOT.value)
    except SdrPayloadError as exc:
        msg = f"error: --render-from: invalid SDR JSON in {token}: {exc}"
        return _fail(is_pipe=is_pipe, exc=exc, message=msg, exit_code=ExitCode.GENERIC.value)

    if is_pipe:
        sys.stdout.write(json.dumps(doc.to_dict(), indent=2, default=str) + "\n")
        sys.stdout.flush()
        return ExitCode.OK.value

    registry.bootstrap()
    if template_path is not None:
        # Same per-run config the generate pipeline sets on the singleton writer.
        tw = registry.get_writer("excel-template")
        tw.template_path = template_path
        tw.organization = template_organization

    rsid = doc.report_suite.rsid
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for fmt in formats:
            writer = registry.get_writer(fmt)
            written.extend(writer.write(doc, output_dir / f"{rsid}{writer.extension}"))
    except OSError as exc:
        return _fail(
            is_pipe=False,
            exc=exc,
            message=f"output error: render write failed for rsid={rsid} at {output_dir}: {exc}",
            exit_code=ExitCode.OUTPUT.value,
        )
    for path in written:
        print(f"wrote: {path}")
    return ExitCode.OK.value


def _load_token(token: str, *, profile: str | None, snapshot_dir: Path | None) -> Any:
    """Return the parsed JSON for `token`.

    An existing file is read as-is, since it may be SDR JSON or an envelope.
    Every other token goes through the snapshot resolver (git refs,
    ``<RSID>@<spec>``, and its not-found messages), which only accepts
    envelopes. Raises SnapshotError subclasses."""
    path = Path(token).expanduser()
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            raise SnapshotResolveError(f"file {path} is not valid JSON: {exc}") from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise SnapshotResolveError(f"could not read {path}: {exc}") from exc

    from aa_auto_sdr.snapshot.resolver import resolve_snapshot

    directory = snapshot_dir
    if directory is None and profile:
        from aa_auto_sdr.core.profiles import default_base

        directory = default_base() / "orgs" / profile / "snapshots"
    return resolve_snapshot(token, profile_snapshot_dir=directory, repo_root=Path.cwd())
