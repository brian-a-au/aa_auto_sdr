"""Per-family coverage state and quality status shared by the report writers.

Pure derivation from an SdrDocument: no I/O, no heavy imports. Every local
report format renders the same rows so a reader can tell a family that was
collected empty apart from one that was excluded, degraded, partial, or of
unknown scope, and can tell "no audit ran" apart from an audit's verdict."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.sdr.quality import SeverityLevel

# Report order (matches the component sections in every writer), with the
# human heading for each family.
FAMILY_HEADINGS: dict[str, str] = {
    "dimensions": "Dimensions",
    "metrics": "Metrics",
    "segments": "Segments",
    "calculated_metrics": "Calculated Metrics",
    "virtual_report_suites": "Virtual Report Suites",
    "classifications": "Classifications",
}


class CoverageState(StrEnum):
    COLLECTED = "collected"
    COLLECTED_EMPTY = "collected_empty"
    EXCLUDED = "excluded"
    DEGRADED = "degraded"
    PARTIAL = "partial"
    UNKNOWN_SCOPE = "unknown_scope"


@dataclass(frozen=True, slots=True)
class CoverageRow:
    family: str
    state: CoverageState
    count: int
    expansion_level: str | None

    @property
    def heading(self) -> str:
        return FAMILY_HEADINGS[self.family]

    @property
    def label(self) -> str:
        """Human-readable state for report readers."""
        match self.state:
            case CoverageState.COLLECTED:
                return "Collected"
            case CoverageState.COLLECTED_EMPTY:
                return "Collected — no components"
            case CoverageState.EXCLUDED:
                return "Not collected in this capture"
            case CoverageState.DEGRADED:
                return "Fetch degraded — no data" if self.count == 0 else "Fetch degraded"
            case CoverageState.PARTIAL:
                if self.expansion_level:
                    return f"Partial fetch (expansion level: {self.expansion_level})"
                return "Partial fetch"
            case CoverageState.UNKNOWN_SCOPE:
                return "Scope unknown — may not have been collected"


def _meta_field(meta: Any, name: str) -> Any:
    if isinstance(meta, dict):
        return meta.get(name)
    return getattr(meta, name, None)


def coverage_rows(doc: SdrDocument) -> list[CoverageRow]:
    """One row per component family, in report order.

    A non-healthy fetch status is definitive (a degraded or partial family was
    collected), so it wins over scope. Otherwise unknown scope stays unknown
    even with zero rows: it is never reported as collected-empty."""
    rows: list[CoverageRow] = []
    scope = doc.collected_components
    for family in FAMILY_HEADINGS:
        count = len(getattr(doc, family))
        meta = doc.fetch_status.get(family)
        status = _meta_field(meta, "status") if meta is not None else None
        level = _meta_field(meta, "expansion_level") if meta is not None else None
        if status == "degraded":
            state = CoverageState.DEGRADED
        elif status == "partial":
            state = CoverageState.PARTIAL
        elif scope is None:
            state = CoverageState.UNKNOWN_SCOPE
        elif family not in scope:
            state = CoverageState.EXCLUDED
        elif count == 0:
            state = CoverageState.COLLECTED_EMPTY
        else:
            state = CoverageState.COLLECTED
        rows.append(
            CoverageRow(
                family=family,
                state=state,
                count=count,
                expansion_level=level if state is CoverageState.PARTIAL else None,
            )
        )
    return rows


@dataclass(frozen=True, slots=True)
class QualityStatus:
    audited: bool
    verdict: str | None = None
    threshold: str | None = None
    total: int = 0
    by_severity: dict[str, int] | None = None
    issues: tuple[dict[str, Any], ...] = ()


def quality_status(quality: dict[str, Any] | None) -> QualityStatus:
    """Summarize `SdrDocument.quality`. `None` means no audit ran.

    Tolerates older quality blocks that predate `issues` / `summary`."""
    if quality is None:
        return QualityStatus(audited=False)
    issues = tuple(i for i in quality.get("issues") or [] if isinstance(i, dict))
    summary = quality.get("summary") or {}
    raw_counts = summary.get("by_severity") or {}
    by_severity = {sev.value: 0 for sev in SeverityLevel}
    if raw_counts:
        for sev in by_severity:
            by_severity[sev] = int(raw_counts.get(sev, 0) or 0)
    else:
        for issue in issues:
            sev = str(issue.get("severity", ""))
            if sev in by_severity:
                by_severity[sev] += 1
    total = summary.get("total")
    return QualityStatus(
        audited=True,
        verdict=summary.get("verdict"),
        threshold=summary.get("policy_threshold"),
        total=int(total) if total is not None else len(issues),
        by_severity=by_severity,
        issues=issues,
    )


def quality_status_line(status: QualityStatus) -> str:
    """One-sentence quality status for report readers."""
    if not status.audited:
        return "No quality audit ran."
    noun = "issue" if status.total == 1 else "issues"
    counts = ", ".join(f"{sev} {n}" for sev, n in (status.by_severity or {}).items())
    findings = f"{status.total} {noun}" + (f" ({counts})" if counts else "")
    if status.verdict in (None, "", "n/a"):
        return f"Quality audit ran with no gate policy: {findings}."
    threshold = f" at threshold {status.threshold}" if status.threshold else ""
    return f"Quality gate {str(status.verdict).upper()}{threshold}: {findings}."


class QualityState(StrEnum):
    """Whether the quality audit ran, for the SDR JSON `coverage.quality.state`.

    `failed` is reserved for parity with cja_auto_sdr: an audit that raises
    fails the whole run today, so no SDR document ever records it."""

    RAN = "ran"
    NOT_RUN = "not_run"
    FAILED = "failed"


def quality_json(status: QualityStatus) -> dict[str, Any]:
    """JSON form of a quality status: `{state, detail, issue_count, severity_counts, gate}`.

    `gate` is None unless a `--fail-on-quality` threshold applied (as in
    cja_auto_sdr). Then it is `{threshold, verdict}` with aa's existing
    summary verdict values (`pass`, `fail`)."""
    if not status.audited:
        return {
            "state": QualityState.NOT_RUN.value,
            "detail": quality_status_line(status),
            "issue_count": None,
            "severity_counts": {},
            "gate": None,
        }
    return {
        "state": QualityState.RAN.value,
        "detail": quality_status_line(status),
        "issue_count": status.total,
        "severity_counts": dict(status.by_severity or {}),
        "gate": ({"threshold": status.threshold, "verdict": status.verdict} if status.threshold is not None else None),
    }


def coverage_json(doc: SdrDocument) -> dict[str, Any]:
    """The SDR JSON `coverage` object: per-family rows plus the quality status."""
    return {
        "families": [
            {"family": row.family, "state": row.state.value, "count": row.count, "detail": row.label}
            for row in coverage_rows(doc)
        ],
        "quality": quality_json(quality_status(doc.quality)),
    }
