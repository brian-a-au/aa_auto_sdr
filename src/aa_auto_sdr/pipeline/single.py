"""Single-RSID pipeline: AaClient → SdrDocument → output files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import timings
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline.models import RunResult
from aa_auto_sdr.sdr.builder import ComponentFilter, build_sdr
from aa_auto_sdr.sdr.quality import SeverityLevel
from aa_auto_sdr.snapshot.git import GitOpResult

if TYPE_CHECKING:
    from aa_auto_sdr.api.cache import ValidationCache


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
    audit_naming: bool = False,  # v1.9.0
    flag_stale: bool = False,  # v1.9.0
    fail_on_quality: SeverityLevel | None = None,  # v1.12.0
    quality_report: str | None = None,  # v1.12.0 — "json" | "csv" | None
    cache: ValidationCache | None = None,  # v1.12.0
    # v1.15.0 — git integration
    git_commit: bool = False,
    git_push: bool = False,
    git_message: str | None = None,
    # v1.16.0 — template-fill writer config
    template_path: Path | None = None,
    template_organization: str | None = None,
    # v1.18.0 — Notion writer per-run config
    notion_force_new: bool = False,
) -> RunResult:
    """Generate an SDR for `rsid` and write it in every requested `format`.

    If `snapshot_dir` is set, also persist the SdrDocument envelope to
    `<snapshot_dir>/<rsid>/<captured_at-fs>.json`.

    v1.12.0: when `quality_report` is set, also emit the standalone quality
    report alongside SDR outputs. When `fail_on_quality` is set, populate
    the returned `quality_verdict` so callers can decide on ExitCode.QUALITY.
    """
    registry.bootstrap()
    if template_path is not None:
        # v1.16.0 — instance-attribute config. The 'excel-template' writer is
        # registered as a singleton; set the per-run attributes before write().
        tw = registry.get_writer("excel-template")
        tw.template_path = template_path
        tw.organization = template_organization
    if "notion" in formats:
        # v1.18.0 — instance-attribute config for the singleton NotionWriter.
        # `--notion-force-new` is threaded onto the registered instance so it
        # applies to every iteration of the format loop below.
        nw = registry.get_writer("notion")
        nw.force_new = bool(notion_force_new)
    with timings.Timer(f"build:{rsid}"):
        doc = build_sdr(
            client,
            rsid,
            captured_at=captured_at,
            tool_version=tool_version,
            component_filter=component_filter,
            audit_naming=audit_naming,
            flag_stale=flag_stale,
            fail_on_quality=fail_on_quality,
            cache=cache,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fmt in formats:
        writer = registry.get_writer(fmt)
        target = output_dir / f"{rsid}{writer.extension}"
        with timings.Timer(f"write:{fmt}:{rsid}"):
            paths.extend(writer.write(doc, target))
    if snapshot_dir is not None:
        from aa_auto_sdr.snapshot.store import save_snapshot

        with timings.Timer(f"snapshot:{rsid}"):
            snap_path = save_snapshot(doc, snapshot_dir=snapshot_dir)
        paths.append(snap_path)

    # v1.15.0 — git commit after snapshot save.
    git_op: GitOpResult | None = None
    if git_commit and snapshot_dir is not None:
        from aa_auto_sdr.snapshot.git import git_commit_snapshot

        with timings.Timer(f"git_commit:{rsid}"):
            git_op = git_commit_snapshot(
                snapshot_dir,
                rsid=rsid,
                message=git_message,
                push=git_push,
            )

    # v1.12.0 — quality report + verdict.
    quality_report_path: Path | None = None
    quality_verdict: str = ""
    if doc.quality is not None:
        if quality_report:
            from aa_auto_sdr.sdr.quality_policy import write_quality_report

            ts = captured_at.strftime("%Y%m%dT%H%M%S")
            target = output_dir / f"quality_report_{rsid}_{ts}.{quality_report}"
            issues_raw = doc.quality.get("issues", [])
            issues = [_rehydrate_issue(d) for d in issues_raw]
            summary = doc.quality.get("summary", {})
            with timings.Timer(f"quality_report:{rsid}"):
                write_quality_report(issues=issues, summary=summary, target=target, fmt=quality_report)
            paths.append(target)
            quality_report_path = target
        verdict = doc.quality.get("summary", {}).get("verdict", "")
        if isinstance(verdict, str):
            quality_verdict = verdict

    return RunResult(
        rsid=rsid,
        success=True,
        outputs=paths,
        report_suite_name=doc.report_suite.name,
        quality_verdict=quality_verdict,
        quality_report_path=quality_report_path,
        git_op=git_op,
    )


def _rehydrate_issue(d: dict):
    """Rebuild an Issue from its to_dict() form (used inside the quality block)."""
    from aa_auto_sdr.sdr.quality import Issue, SeverityLevel

    return Issue(
        severity=SeverityLevel(d["severity"]),
        category=d["category"],
        type=d["type"],
        item_id=d["item_id"],
        item_name=d["item_name"],
        issue=d["issue"],
        details=d.get("details", {}),
    )
