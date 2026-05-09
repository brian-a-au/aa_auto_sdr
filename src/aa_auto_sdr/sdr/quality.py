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

import re
from typing import Any, Protocol

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
    # snake_case: contains underscore, all lowercase, starts with a letter
    if "_" in name and name == name.lower() and name[0].isalpha():
        return "snake_case"
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

    # Recommendations: flag mixed case styles whenever more than one style is present.
    styles = audit["case_styles"]
    nonzero = {s: c for s, c in styles.items() if c > 0}
    if len(nonzero) >= 2:
        majority_style, majority_count = max(nonzero.items(), key=lambda kv: kv[1])
        minority_parts = ", ".join(f"{s}: {c}" for s, c in nonzero.items() if s != majority_style)
        audit["recommendations"].append(
            f"Mixed case styles detected ({majority_style}: {majority_count}, "
            f"{minority_parts}). Consider standardizing on a single style.",
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
