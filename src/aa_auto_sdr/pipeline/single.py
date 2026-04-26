"""Single-RSID pipeline: AaClient → SdrDocument → output files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline.models import RunResult
from aa_auto_sdr.sdr.builder import build_sdr


def run_single(
    *,
    client: AaClient,
    rsid: str,
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
) -> RunResult:
    """Generate an SDR for `rsid` and write it in every requested `format`."""
    registry.bootstrap()
    doc = build_sdr(client, rsid, captured_at=captured_at, tool_version=tool_version)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fmt in formats:
        writer = registry.get_writer(fmt)
        target = output_dir / f"{rsid}{writer.extension}"
        paths.append(writer.write(doc, target))
    return RunResult(rsid=rsid, success=True, outputs=paths)
