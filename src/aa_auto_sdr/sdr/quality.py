"""Per-RSID component quality audits.

Pure functions — no I/O, no API calls. Inputs are the normalized
component lists already fetched by sdr/builder.py for the SDR document.
Outputs are dicts attached to SdrDocument.quality.

Mirrors cja_auto_sdr/org/analyzer.py::_audit_naming_conventions and
::_detect_stale_components, with AA's component model substituted for
cja's data-view-scoped index.

See docs/superpowers/specs/2026-05-09-aa-auto-sdr-v1.9.0-design.md §3.2.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from aa_auto_sdr.api.cache import ValidationCache

logger = logging.getLogger(__name__)


class SeverityLevel(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


_SEVERITY_RANK = {sev: i for i, sev in enumerate(SeverityLevel)}
_SEVERITY_TABLE_VERSION = "v1.12.0"


@dataclass(frozen=True, slots=True)
class Issue:
    """One severity-tagged quality finding.

    `item_id` references a real component (e.g. `evar5`, `event12`) for
    per-component findings, OR the component-type bundle name (e.g.
    `dimensions`) for bundle-level findings such as case_inconsistency.
    `item_name` is empty for bundle-level findings.
    """

    severity: SeverityLevel
    category: str
    type: str
    item_id: str
    item_name: str
    issue: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "type": self.type,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "issue": self.issue,
            "details": dict(self.details),
        }


def has_quality_issues_at_or_above(issues: list[Issue], threshold: SeverityLevel) -> bool:
    """Returns True if any issue's severity has rank <= threshold's rank."""
    threshold_rank = _SEVERITY_RANK[threshold]
    return any(_SEVERITY_RANK[i.severity] <= threshold_rank for i in issues)


_STALE_KEYWORD_SEVERITY: dict[str, SeverityLevel] = {
    "test": SeverityLevel.MEDIUM,
    "old": SeverityLevel.MEDIUM,
    "deprecated": SeverityLevel.MEDIUM,
    "legacy": SeverityLevel.MEDIUM,
    "obsolete": SeverityLevel.MEDIUM,
    "unused": SeverityLevel.MEDIUM,
    "temp": SeverityLevel.LOW,
    "backup": SeverityLevel.LOW,
    "copy": SeverityLevel.LOW,
    "archive": SeverityLevel.LOW,
}


def _severity_for_stale_reason(reason: str) -> SeverityLevel:
    """Map a v1.9.0 reason string to a SeverityLevel.

    Reasons are colon-prefixed: 'stale_keyword:<kw>', 'version_suffix:vN',
    'date_pattern:<m>'. Unknown prefixes default to LOW (defensive).
    """
    kind, _, value = reason.partition(":")
    if kind == "stale_keyword":
        return _STALE_KEYWORD_SEVERITY.get(value, SeverityLevel.LOW)
    if kind in ("version_suffix", "date_pattern"):
        return SeverityLevel.LOW
    return SeverityLevel.LOW


def _severity_for_case_inconsistency() -> SeverityLevel:
    return SeverityLevel.LOW


# Verbatim from cja_auto_sdr/org/analyzer.py — keeps cross-tool audit
# semantics aligned. If cja drifts, drift here too in the same change.
_STALE_KEYWORDS_RE = re.compile(
    r"(^|[_\-\s])(test|old|temp|tmp|backup|copy|deprecated|legacy|"
    r"archive|obsolete|unused)([_\-\s]|$)",
    re.IGNORECASE,
)
_VERSION_SUFFIX_RE = re.compile(r"[_\-]v\d+$", re.IGNORECASE)
_DATE_PATTERN_RE = re.compile(r"[_\-]?(20\d{2}[01]\d[0-3]\d|20\d{2}[_\-][01]\d[_\-][0-3]\d)([_\-]|$)")

# Component-type label used in stale detection output. Maps the bundle attr
# name to a singular label for human-readable output.
#
# virtual_report_suites are deliberately excluded — VRS are rsid-scoped
# identifiers, not user-authored component names; auditing them as
# "components" produces misleading case-style and prefix counts.
_COMPONENT_TYPE_LABEL = {
    "dimensions": "dimension",
    "metrics": "metric",
    "segments": "segment",
    "calculated_metrics": "calculated_metric",
    "classifications": "classification",
}


class _ComponentBundle(Protocol):
    """Structural type matching SdrDocument's component attributes."""

    dimensions: list[Any]
    metrics: list[Any]
    segments: list[Any]
    calculated_metrics: list[Any]
    classifications: list[Any]


def _iter_components(bundle: _ComponentBundle):
    """Yield (component, type_label) pairs from a bundle."""
    for attr, label in _COMPONENT_TYPE_LABEL.items():
        for c in getattr(bundle, attr, []):
            yield c, label


def _name_or_id(comp: Any) -> str:
    return getattr(comp, "name", None) or getattr(comp, "id", "")


def _detect_case_style(name: str) -> str:
    if not name:
        return "other"
    if not name[0].isalpha():
        return "other"
    if "_" in name and name == name.lower():
        return "snake_case"
    if name == name.upper():
        # ALLCAPS like 'RSID', 'ORDERS' — neither PascalCase nor snake_case
        return "other"
    if name[0].islower() and any(c.isupper() for c in name):
        return "camelCase"
    if name[0].isupper() and any(c.isupper() for c in name[1:]):
        return "PascalCase"
    return "other"


def _detect_prefix(name: str) -> str:
    if "/" in name:
        return name.split("/", 1)[0].lower()
    if "_" in name:
        return name.split("_", 1)[0].lower()
    if len(name) > 3:
        return name[:3].lower()
    return "other"


def audit_naming(bundle: _ComponentBundle) -> dict[str, Any]:
    """Return naming-audit dict.

    Structure:
      {
        "total_components": int,
        "case_styles": {snake_case: int, camelCase: int, PascalCase: int, other: int},
        "prefix_groups": {prefix: count, ...},
        "recommendations": [str, ...],
      }
    """
    audit: dict[str, Any] = {
        "total_components": 0,
        "case_styles": {"snake_case": 0, "camelCase": 0, "PascalCase": 0, "other": 0},
        "prefix_groups": {},
        "recommendations": [],
    }

    for comp, _ in _iter_components(bundle):
        name = _name_or_id(comp)
        if not name:
            continue
        audit["total_components"] += 1
        audit["case_styles"][_detect_case_style(name)] += 1
        prefix = _detect_prefix(name)
        audit["prefix_groups"][prefix] = audit["prefix_groups"].get(prefix, 0) + 1

    # Recommendation rule: any minority case style triggers the rec. Stricter
    # ratio-based thresholding (e.g., "minority must exceed 20%") is deferred
    # to v1.12.0's quality severity engine, where severity scoring formalizes
    # what counts as actionable. v1.9.0 ships the read-only signal only.
    styles = audit["case_styles"]
    nonzero = {s: c for s, c in styles.items() if c > 0}
    if len(nonzero) >= 2:
        majority_style, majority_count = max(nonzero.items(), key=lambda kv: kv[1])
        for style, count in nonzero.items():
            if style == majority_style:
                continue
            audit["recommendations"].append(
                f"Mixed case styles detected ({majority_style}: {majority_count}, "
                f"{style}: {count}). Consider standardizing on a single style.",
            )
            break  # one rec is enough

    return audit


def detect_stale(bundle: _ComponentBundle) -> list[dict[str, Any]]:
    """Return list of stale-component dicts.

    Each entry: {"id": str, "name": str, "type": str, "reasons": [str, ...]}
    Reasons drawn from {stale_keyword:<keyword>, version_suffix:v<N>, date_pattern:<...>}.
    """
    out: list[dict[str, Any]] = []
    for comp, label in _iter_components(bundle):
        name = _name_or_id(comp)
        if not name:
            continue
        reasons: list[str] = []
        m = _STALE_KEYWORDS_RE.search(name)
        if m:
            reasons.append(f"stale_keyword:{m.group(2).lower()}")
        m = _VERSION_SUFFIX_RE.search(name)
        if m:
            reasons.append(f"version_suffix:{m.group(0).lstrip('_-').lower()}")
        m = _DATE_PATTERN_RE.search(name)
        if m:
            reasons.append(f"date_pattern:{m.group(1)}")
        if reasons:
            out.append(
                {
                    "id": getattr(comp, "id", ""),
                    "name": name,
                    "type": label,
                    "reasons": reasons,
                },
            )
    return out


def run_audits(
    bundle: _ComponentBundle,
    *,
    audit_naming_enabled: bool,
    flag_stale_enabled: bool,
    fail_on_quality: SeverityLevel | None = None,
    cache: ValidationCache | None = None,
    rsid: str = "",
) -> dict[str, Any]:
    """Compose v1.9.0 audits + v1.12.0 severity-promotion into the
    SdrDocument.quality block shape.

    Returns the full quality dict with v1.9.0 keys (`naming_audit`,
    `stale_components`) plus v1.12.0 keys (`issues`, `summary`).
    """
    # Defensive: a cache without rsid leaks across RSIDs; disable it.
    if cache is not None and not rsid:
        cache = None

    # Cache lookup before any audit work.
    cache_key = ""
    if cache is not None and rsid:
        flat: list[Any] = []
        for ctype in ("dimensions", "metrics", "segments", "calculated_metrics", "classifications"):
            flat.extend(getattr(bundle, ctype, []) or [])
        cache_key = _cache_key(
            rsid=rsid,
            component_type=(
                f"all:{audit_naming_enabled}:{flag_stale_enabled}:"
                f"{fail_on_quality.value if fail_on_quality else 'NONE'}"
            ),
            items=flat,
            severity_table_version=_SEVERITY_TABLE_VERSION,
        )
        hit = cache.get(cache_key)
        if hit is not None:
            return hit

    naming = audit_naming(bundle) if audit_naming_enabled else _empty_naming()
    stale = detect_stale(bundle) if flag_stale_enabled else []

    issues: list[Issue] = []
    issues.extend(_promote_stale_to_issues(stale))
    issues.extend(_promote_naming_to_issues(naming))

    by_severity: dict[str, int] = {sev.value: 0 for sev in SeverityLevel}
    for i in issues:
        by_severity[i.severity.value] += 1
    total = len(issues)

    summary: dict[str, Any] = {
        "by_severity": by_severity,
        "total": total,
        "verdict": "n/a",
    }
    if fail_on_quality is not None:
        summary["policy_threshold"] = fail_on_quality.value
        summary["verdict"] = "fail" if has_quality_issues_at_or_above(issues, fail_on_quality) else "pass"

    quality_block = {
        "naming_audit": naming,
        "stale_components": stale,
        "issues": [i.to_dict() for i in issues],
        "summary": summary,
    }

    # Per spec §3.12 — fires after every audit run. `rsid` included so
    # multi-RSID batch logs can be correlated by RSID; empty string when the
    # caller didn't supply one (e.g., direct `run_audits(...)` use in tests).
    # Format-string keys are aligned with extras keys so the canonical-event
    # validator (tests/core/test_logging_vocabulary.py) sees a clean match.
    logger.info(
        "quality_audit_complete rsid=%s quality_total=%s quality_by_severity=%s",
        rsid,
        total,
        by_severity,
        extra={
            "rsid": rsid,
            "quality_total": total,
            "quality_by_severity": by_severity,
        },
    )
    # Per spec §3.12 — fires only when --fail-on-quality was set.
    if fail_on_quality is not None:
        logger.info(
            "quality_gate_evaluated rsid=%s threshold=%s verdict=%s",
            rsid,
            fail_on_quality.value,
            summary["verdict"],
            extra={
                "rsid": rsid,
                "threshold": fail_on_quality.value,
                "verdict": summary["verdict"],
            },
        )

    if cache is not None and rsid and cache_key:
        cache.put(cache_key, quality_block)
    return quality_block


def _empty_naming() -> dict[str, Any]:
    return {
        "total_components": 0,
        "case_styles": {},
        "prefix_groups": {},
        "recommendations": [],
    }


def _promote_stale_to_issues(stale: list[dict[str, Any]]) -> list[Issue]:
    out: list[Issue] = []
    for s in stale:
        for reason in s["reasons"]:
            severity = _severity_for_stale_reason(reason)
            kind, _, value = reason.partition(":")
            out.append(
                Issue(
                    severity=severity,
                    category="stale",
                    type=kind,
                    item_id=s["id"],
                    item_name=s["name"],
                    issue=f"Component name matches {kind} pattern: {value}",
                    details={"component_type": s["type"], "reason": reason},
                ),
            )
    return out


def _promote_naming_to_issues(naming: dict[str, Any]) -> list[Issue]:
    return [
        Issue(
            severity=_severity_for_case_inconsistency(),
            category="naming",
            type="case_inconsistency",
            item_id="naming_audit",
            item_name="",
            issue=rec,
            details={},
        )
        for rec in naming.get("recommendations", [])
    ]


def _id_of(item: object) -> str:
    """Adapter — every aa component dataclass exposes `.id` (see api/models.py);
    fall back to repr for foreign objects."""
    if hasattr(item, "id"):
        return str(item.id)
    return repr(item)


def _cache_key(
    rsid: str,
    component_type: str,
    items: list[Any],
    severity_table_version: str,
) -> str:
    """Stable per-bundle key. Hashes sorted (id, name) pairs + severity table
    version: the audits are name-based, so a rename (same id) must invalidate,
    and a policy/severity-table change invalidates everything."""
    import hashlib

    entries = sorted(f"{_id_of(it)}\x1f{getattr(it, 'name', '')}" for it in items)
    digest = hashlib.sha1(  # noqa: S324 (cache key, not security-sensitive)
        (rsid + component_type + "\x1e".join(entries) + severity_table_version).encode(),
    ).hexdigest()[:16]
    return f"quality_v1:{rsid}:{component_type}:{digest}"
