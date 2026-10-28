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

import dataclasses
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Protocol

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

# Stable rule IDs, keyed by finding `type`. Scheme matches cja_auto_sdr:
# `dq.<snake_rule>.v<N>`. Bump N only when a rule's meaning changes (what it
# flags or why), never for wording or severity tweaks, so exceptions and
# downstream filters keyed on a rule ID keep meaning the same thing.
QUALITY_RULE_IDS: Final[dict[str, str]] = {
    "stale_keyword": "dq.stale_keyword.v1",
    "version_suffix": "dq.version_suffix.v1",
    "date_pattern": "dq.date_pattern.v1",
    "case_inconsistency": "dq.naming_case_inconsistency.v1",
    "naming_convention": "dq.naming_convention.v1",
}
CUSTOM_RULE_ID: Final = "dq.custom.unknown"
KNOWN_RULE_IDS: Final[frozenset[str]] = frozenset(QUALITY_RULE_IDS.values())

# Default severity for `dq.naming_convention.v1` findings: a house-style miss,
# the same weight as the bundle-level case_inconsistency finding.
NAMING_CONVENTION_SEVERITY: Final = SeverityLevel.LOW

# The six component families a policy may target (naming rules and
# component_type exceptions). Same names as SdrDocument's attributes.
COMPONENT_FAMILIES: Final[tuple[str, ...]] = (
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
)

CASE_STYLES: Final[tuple[str, ...]] = ("snake_case", "camelCase", "PascalCase", "Title Case", "kebab-case", "any")

_CASE_STYLE_RE: dict[str, re.Pattern[str]] = {
    "snake_case": re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"),
    "camelCase": re.compile(r"[a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)*"),
    "PascalCase": re.compile(r"[A-Z][a-z0-9]*(?:[A-Z][a-z0-9]*)*"),
    "kebab-case": re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"),
}


def rule_id_for(finding_type: str) -> str:
    """Rule ID for a finding `type`; `dq.custom.unknown` when unrecognized."""
    return QUALITY_RULE_IDS.get(finding_type, CUSTOM_RULE_ID)


# Lowercase words Title Case allows after the first word, so Adobe names such
# as "Time Spent per Visit" pass.
TITLE_CASE_SMALL_WORDS: Final[frozenset[str]] = frozenset(
    {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "per", "the", "to", "vs", "via", "with"},
)


def matches_case_style(name: str, style: str) -> bool:
    """True when `name` follows `style` (one of CASE_STYLES).

    `Title Case` means every space-separated word that starts with a letter
    starts with a capital letter, except the small words in
    TITLE_CASE_SMALL_WORDS when they are not the first word; words starting
    with a digit or punctuation are ignored. The other styles are ASCII-only
    regexes. `any` always matches."""
    if style == "any":
        return True
    if style == "Title Case":
        words = name.split(" ")
        return bool(name) and all(
            w and (not w[0].isalpha() or w[0].isupper() or (idx > 0 and w in TITLE_CASE_SMALL_WORDS))
            for idx, w in enumerate(words)
        )
    return _CASE_STYLE_RE[style].fullmatch(name) is not None


@dataclass(frozen=True, slots=True)
class NamingRule:
    """Per-family naming convention. `case` "any" (or None) skips the case
    check; `pattern` is a regex the component name must fully match."""

    case: str | None = None
    pattern: str | None = None


@dataclass(frozen=True, slots=True)
class QualityException:
    """A reasoned exception: findings of `rule_id` on one component
    (`component_id`) or a whole family (`component_type`) stay visible but
    are marked excepted and do not count toward the gate."""

    rule_id: str
    reason: str
    component_id: str | None = None
    component_type: str | None = None

    def covers(self, family: str, component_id: str) -> bool:
        if self.component_id is not None:
            return self.component_id == component_id
        return self.component_type == family


@dataclass(frozen=True, slots=True)
class QualityRules:
    """Effective policy rules evaluated by run_audits."""

    naming: dict[str, NamingRule] = field(default_factory=dict)
    exceptions: tuple[QualityException, ...] = ()

    def fingerprint(self) -> str:
        """Stable hash of the rules, used in the validation cache key."""
        payload = {
            "naming": {k: [v.case, v.pattern] for k, v in sorted(self.naming.items())},
            "exceptions": [[e.rule_id, e.component_id, e.component_type, e.reason] for e in self.exceptions],
        }
        return hashlib.sha1(  # noqa: S324 (cache key, not security-sensitive)
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class Issue:
    """One severity-tagged quality finding.

    `item_id` references a real component (e.g. `evar5`, `event12`) for
    per-component findings, OR the component-type bundle name (e.g.
    `dimensions`) for bundle-level findings such as case_inconsistency.
    `item_name` is empty for bundle-level findings.

    `component_ids` lists the affected components (sorted) and `occurrences`
    counts them. `members` holds (family, id) pairs used only to match
    exceptions; it is not serialized.
    """

    severity: SeverityLevel
    category: str
    type: str
    item_id: str
    item_name: str
    issue: str
    details: dict[str, Any] = field(default_factory=dict)
    rule_id: str | None = None
    component_ids: tuple[str, ...] = ()
    occurrences: int = 1
    excepted: bool = False
    exception_reason: str | None = None
    members: tuple[tuple[str, str], ...] = field(default=(), compare=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "type": self.type,
            "item_id": self.item_id,
            "item_name": self.item_name,
            "issue": self.issue,
            "details": dict(self.details),
            "rule_id": self.rule_id or rule_id_for(self.type),
            "component_ids": list(self.component_ids),
            "occurrences": self.occurrences,
            "excepted": self.excepted,
            "exception_reason": self.exception_reason,
        }


def has_quality_issues_at_or_above(issues: list[Issue], threshold: SeverityLevel) -> bool:
    """True if any non-excepted issue's severity has rank <= threshold's rank."""
    threshold_rank = _SEVERITY_RANK[threshold]
    return any(not i.excepted and _SEVERITY_RANK[i.severity] <= threshold_rank for i in issues)


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
    if name[0].isupper() and name.isascii() and name.isalnum():
        # A single capitalized word (Adobe's standard 'Visits', 'Day') is
        # valid PascalCase; without this every report suite reports its
        # built-in names as a case inconsistency.
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

    # Recommendation rule: any minority case style triggers the rec. One rec
    # names the majority style and every minority style with its count.
    styles = audit["case_styles"]
    nonzero = {s: c for s, c in styles.items() if c > 0}
    if len(nonzero) >= 2:
        majority_style, majority_count = max(nonzero.items(), key=lambda kv: kv[1])
        minority = ", ".join(
            f"{style}: {count}"
            for style, count in sorted(nonzero.items(), key=lambda kv: -kv[1])
            if style != majority_style
        )
        audit["recommendations"].append(
            f"Mixed case styles detected ({majority_style}: {majority_count}, "
            f"{minority}). Consider standardizing on a single style.",
        )

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
    rules: QualityRules | None = None,
) -> dict[str, Any]:
    """Compose v1.9.0 audits + v1.12.0 severity-promotion into the
    SdrDocument.quality block shape.

    Returns the full quality dict with v1.9.0 keys (`naming_audit`,
    `stale_components`) plus v1.12.0 keys (`issues`, `summary`).

    `rules` (from the policy file) adds per-family naming-convention
    findings when the naming audit runs, and marks findings covered by a
    reasoned exception as excepted. Excepted findings stay in `issues` but
    are left out of `summary.by_severity` / `summary.total` and the gate;
    `summary.excepted` counts them.
    """
    # Defensive: a cache without rsid leaks across RSIDs; disable it.
    if cache is not None and not rsid:
        cache = None

    # Cache lookup before any audit work.
    cache_key = ""
    if cache is not None:
        # Keep component types separate: identical IDs/names in different
        # sections produce different stale-component labels.
        section_keys = ":".join(
            _cache_key(rsid, ctype, getattr(bundle, ctype, []) or [], _SEVERITY_TABLE_VERSION)
            for ctype in _COMPONENT_TYPE_LABEL
        )
        # VRS is not part of the default audit sections but naming rules may
        # target it, so it joins the key only when rules are present.
        if rules is not None and "virtual_report_suites" in rules.naming:
            section_keys += ":" + _cache_key(
                rsid,
                "virtual_report_suites",
                getattr(bundle, "virtual_report_suites", []) or [],
                _SEVERITY_TABLE_VERSION,
            )
        cache_key = (
            f"{audit_naming_enabled}:{flag_stale_enabled}:"
            f"{fail_on_quality.value if fail_on_quality else 'NONE'}:"
            f"{rules.fingerprint() if rules is not None else 'NORULES'}:{section_keys}"
        )
        hit = cache.get(cache_key)
        if hit is not None:
            return hit

    naming = audit_naming(bundle) if audit_naming_enabled else _empty_naming()
    stale = detect_stale(bundle) if flag_stale_enabled else []

    issues: list[Issue] = []
    issues.extend(_promote_stale_to_issues(stale))
    issues.extend(
        _promote_naming_to_issues(naming, _case_minority_members(bundle) if naming["recommendations"] else ())
    )
    if audit_naming_enabled and rules is not None and rules.naming:
        issues.extend(_naming_convention_issues(bundle, rules.naming))
    if rules is not None and rules.exceptions:
        issues = [_apply_exceptions(i, rules.exceptions) for i in issues]
        _warn_unmatched_exceptions(
            issues,
            rules.exceptions,
            rsid=rsid,
            audit_naming_enabled=audit_naming_enabled,
            flag_stale_enabled=flag_stale_enabled,
        )

    by_severity: dict[str, int] = {sev.value: 0 for sev in SeverityLevel}
    excepted = 0
    for i in issues:
        if i.excepted:
            excepted += 1
        else:
            by_severity[i.severity.value] += 1
    total = len(issues) - excepted

    summary: dict[str, Any] = {
        "by_severity": by_severity,
        "total": total,
        "excepted": excepted,
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

    if cache is not None:
        cache.put(cache_key, quality_block)
    return quality_block


def _empty_naming() -> dict[str, Any]:
    return {
        "total_components": 0,
        "case_styles": {},
        "prefix_groups": {},
        "recommendations": [],
    }


_LABEL_TO_FAMILY = {label: family for family, label in _COMPONENT_TYPE_LABEL.items()}
_FAMILY_LABEL = {**_COMPONENT_TYPE_LABEL, "virtual_report_suites": "virtual_report_suite"}


def _promote_stale_to_issues(stale: list[dict[str, Any]]) -> list[Issue]:
    out: list[Issue] = []
    for s in stale:
        family = _LABEL_TO_FAMILY.get(s["type"], s["type"])
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
                    rule_id=rule_id_for(kind),
                    component_ids=(s["id"],),
                    occurrences=1,
                    members=((family, s["id"]),),
                ),
            )
    return out


def _case_minority_members(bundle: _ComponentBundle) -> tuple[tuple[str, str], ...]:
    """(family, id) of every audited component outside the majority case style.

    Mirrors audit_naming's majority choice (max count; ties go to the first
    style in snake_case, camelCase, PascalCase, other order). Only called
    when audit_naming produced a recommendation, so two or more styles exist."""
    styled: list[tuple[str, str, str]] = []
    counts = {"snake_case": 0, "camelCase": 0, "PascalCase": 0, "other": 0}
    for family in _COMPONENT_TYPE_LABEL:
        for comp in getattr(bundle, family, []):
            name = _name_or_id(comp)
            if not name:
                continue
            style = _detect_case_style(name)
            counts[style] += 1
            styled.append((family, str(getattr(comp, "id", "")), style))
    nonzero = {s: c for s, c in counts.items() if c > 0}
    majority = max(nonzero.items(), key=lambda kv: kv[1])[0]
    return tuple((family, cid) for family, cid, style in styled if style != majority)


def _promote_naming_to_issues(
    naming: dict[str, Any],
    members: tuple[tuple[str, str], ...] = (),
) -> list[Issue]:
    ids = tuple(sorted({cid for _, cid in members}))
    return [
        Issue(
            severity=SeverityLevel.LOW,
            category="naming",
            type="case_inconsistency",
            item_id="naming_audit",
            item_name="",
            issue=rec,
            details={},
            rule_id=rule_id_for("case_inconsistency"),
            component_ids=ids,
            occurrences=len(members),
            members=members,
        )
        for rec in naming.get("recommendations", [])
    ]


def _is_standard_component(comp: Any) -> bool:
    """True only when the API said so; absent means unknown, not standard."""
    extra = getattr(comp, "extra", None)
    return isinstance(extra, dict) and extra.get("standardComponent") is True


def _naming_convention_issues(bundle: Any, naming_rules: dict[str, NamingRule]) -> list[Issue]:
    """One `dq.naming_convention.v1` finding per component whose name breaks
    its family's rule. Known Adobe standard components are skipped."""
    out: list[Issue] = []
    for family in COMPONENT_FAMILIES:
        rule = naming_rules.get(family)
        if rule is None:
            continue
        case = rule.case if rule.case not in (None, "any") else None
        for comp in getattr(bundle, family, []) or []:
            name = getattr(comp, "name", None) or ""
            if not name or _is_standard_component(comp):
                continue
            violations: list[str] = []
            if case is not None and not matches_case_style(name, case):
                violations.append("case")
            if rule.pattern is not None and re.fullmatch(rule.pattern, name) is None:
                violations.append("pattern")
            if not violations:
                continue
            cid = str(getattr(comp, "id", ""))
            expected = " and ".join(
                part
                for part in (
                    case if "case" in violations else "",
                    f"pattern {rule.pattern}" if "pattern" in violations else "",
                )
                if part
            )
            details: dict[str, Any] = {"component_type": _FAMILY_LABEL[family], "violations": violations}
            if case is not None:
                details["expected_case"] = case
            if rule.pattern is not None:
                details["pattern"] = rule.pattern
            out.append(
                Issue(
                    severity=NAMING_CONVENTION_SEVERITY,
                    category="naming",
                    type="naming_convention",
                    item_id=cid,
                    item_name=name,
                    issue=f"Name does not follow the {family} naming rule: expected {expected}",
                    details=details,
                    rule_id=rule_id_for("naming_convention"),
                    component_ids=(cid,),
                    occurrences=1,
                    members=((family, cid),),
                ),
            )
    return out


_STALE_RULE_IDS = frozenset(QUALITY_RULE_IDS[t] for t in ("stale_keyword", "version_suffix", "date_pattern"))


def _warn_unmatched_exceptions(
    issues: list[Issue],
    exceptions: tuple[QualityException, ...],
    *,
    rsid: str,
    audit_naming_enabled: bool,
    flag_stale_enabled: bool,
) -> None:
    """WARNING for each exception that covers no affected component of any
    finding of its rule (usually a typo). Silent for rules whose audit did
    not run, since nothing could have matched."""
    for exc in exceptions:
        ran = flag_stale_enabled if exc.rule_id in _STALE_RULE_IDS else audit_naming_enabled
        if not ran:
            continue
        matched = any(
            (i.rule_id or rule_id_for(i.type)) == exc.rule_id and any(exc.covers(f, c) for f, c in i.members)
            for i in issues
        )
        if matched:
            continue
        logger.warning(
            "quality_exception_unmatched rsid=%s rule_id=%s component_id=%s component_type=%s",
            rsid,
            exc.rule_id,
            exc.component_id,
            exc.component_type,
            extra={
                "rsid": rsid,
                "rule_id": exc.rule_id,
                "component_id": exc.component_id,
                "component_type": exc.component_type,
            },
        )


def _apply_exceptions(issue: Issue, exceptions: tuple[QualityException, ...]) -> Issue:
    """Mark `issue` excepted when every affected component is covered by an
    exception for its rule. The first matching exception's reason is kept."""
    rule_id = issue.rule_id or rule_id_for(issue.type)
    candidates = [e for e in exceptions if e.rule_id == rule_id]
    if not candidates or not issue.members:
        return issue
    reason: str | None = None
    for family, cid in issue.members:
        match = next((e for e in candidates if e.covers(family, cid)), None)
        if match is None:
            return issue
        reason = reason or match.reason
    return dataclasses.replace(issue, excepted=True, exception_reason=reason)


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
    """Hash a section's ordered identities/names and severity-table version.

    Order affects issue ordering. JSON framing avoids collisions when a name
    or ID contains separators. A rename, a change in the known
    standard-component flag, or a severity-table change invalidates.
    """
    entries = [(_id_of(it), getattr(it, "name", ""), _is_standard_component(it)) for it in items]
    digest = hashlib.sha1(  # noqa: S324 (cache key, not security-sensitive)
        json.dumps([rsid, component_type, entries, severity_table_version], separators=(",", ":")).encode(),
    ).hexdigest()[:16]
    return f"quality_v1:{rsid}:{component_type}:{digest}"
