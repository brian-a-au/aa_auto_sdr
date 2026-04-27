"""Single-RSID pipeline: AaClient → SdrDocument → output files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline.models import RunResult
from aa_auto_sdr.sdr.builder import ComponentFilter, build_sdr


def run_single(
    *,
    client: AaClient,
    rsid: str,
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
    snapshot_dir: Path | None = None,
    component_filter: ComponentFilter | None = None,  # v1.2
) -> RunResult:
    """Generate an SDR for `rsid` and write it in every requested `format`.

    If `snapshot_dir` is set, also persist the SdrDocument envelope to
    `<snapshot_dir>/<rsid>/<captured_at-fs>.json`."""
    registry.bootstrap()
    doc = build_sdr(
        client,
        rsid,
        captured_at=captured_at,
        tool_version=tool_version,
        component_filter=component_filter,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fmt in formats:
        writer = registry.get_writer(fmt)
        target = output_dir / f"{rsid}{writer.extension}"
        paths.extend(writer.write(doc, target))
    if snapshot_dir is not None:
        from aa_auto_sdr.snapshot.store import save_snapshot

        snap_path = save_snapshot(doc, snapshot_dir=snapshot_dir)
        paths.append(snap_path)
    return RunResult(
        rsid=rsid,
        success=True,
        outputs=paths,
        report_suite_name=doc.report_suite.name,
    )
