"""Quality-engine policy loader, defaults application, and report writer.

Mirrors cja_auto_sdr/api/quality_policy.py at the contract level — JSON
file with `fail_on_quality` / `quality_report` keys, CLI-wins precedence,
hyphen/underscore canonicalization, optional `quality_policy` /
`quality` envelope nesting. aa drops `max_issues` and `allow_partial`
per spec §2.2.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from aa_auto_sdr.core.atomic_io import atomic_write_text
from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.sdr.quality import (
    CASE_STYLES,
    COMPONENT_FAMILIES,
    KNOWN_RULE_IDS,
    Issue,
    NamingRule,
    QualityException,
    QualityRules,
    SeverityLevel,
)

_VALID_REPORT_FORMATS = ("json", "csv")
_KNOWN_KEYS = {"fail_on_quality", "quality_report", "naming", "exceptions"}
_DROPPED_KEYS = {"max_issues", "allow_partial"}
_NAMING_RULE_KEYS = {"case", "pattern"}
_EXCEPTION_KEYS = {"rule_id", "component_id", "component_type", "reason"}
# Original six columns first; later columns are additive.
_REPORT_CSV_HEADERS = [
    "severity",
    "category",
    "type",
    "item_id",
    "item_name",
    "issue",
    "rule_id",
    "component_ids",
    "occurrences",
    "excepted",
    "exception_reason",
]


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    fail_on_quality: SeverityLevel | None = None
    quality_report: Literal["json", "csv"] | None = None
    naming: dict[str, NamingRule] = field(default_factory=dict)
    exceptions: tuple[QualityException, ...] = ()

    @property
    def rules(self) -> QualityRules | None:
        """Naming rules + exceptions for run_audits; None when the policy has neither."""
        if not self.naming and not self.exceptions:
            return None
        return QualityRules(naming=dict(self.naming), exceptions=self.exceptions)


def _parse_naming(raw: Any) -> dict[str, NamingRule]:
    if not isinstance(raw, dict):
        raise ConfigError("--quality-policy: naming must be an object keyed by component type.")
    out: dict[str, NamingRule] = {}
    for key, rule in raw.items():
        family = str(key).replace("-", "_")
        if family not in COMPONENT_FAMILIES:
            raise ConfigError(
                f"--quality-policy: naming has unknown component type {key!r}. Allowed: {list(COMPONENT_FAMILIES)}.",
            )
        where = f"naming.{family}"
        if not isinstance(rule, dict):
            raise ConfigError(f"--quality-policy: {where} must be an object with case and/or pattern.")
        unknown = set(rule) - _NAMING_RULE_KEYS
        if unknown:
            raise ConfigError(
                f"--quality-policy: {where} has unknown key(s): {sorted(unknown)}. Allowed: {sorted(_NAMING_RULE_KEYS)}.",
            )
        if not rule:
            raise ConfigError(f"--quality-policy: {where} must set case and/or pattern.")
        case = rule.get("case")
        if "case" in rule and (not isinstance(case, str) or case not in CASE_STYLES):
            raise ConfigError(
                f"--quality-policy: {where}.case must be a case style in {list(CASE_STYLES)}, got {case!r}.",
            )
        pattern = rule.get("pattern")
        if "pattern" in rule:
            if not isinstance(pattern, str) or not pattern:
                raise ConfigError(f"--quality-policy: {where}.pattern must be a non-empty regex string.")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(
                    f"--quality-policy: {where}.pattern is an invalid regex ({exc}): {pattern!r}"
                ) from exc
        out[family] = NamingRule(case=case, pattern=pattern)
    return out


def _parse_exceptions(raw: Any) -> tuple[QualityException, ...]:
    if not isinstance(raw, list):
        raise ConfigError("--quality-policy: exceptions must be a list of objects.")
    out: list[QualityException] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for idx, entry in enumerate(raw):
        where = f"exceptions[{idx}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"--quality-policy: {where} must be an object.")
        item = {str(k).replace("-", "_"): v for k, v in entry.items()}
        unknown = set(item) - _EXCEPTION_KEYS
        if unknown:
            raise ConfigError(
                f"--quality-policy: {where} has unknown key(s): {sorted(unknown)}. Allowed: {sorted(_EXCEPTION_KEYS)}.",
            )
        rule_id = item.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ConfigError(f"--quality-policy: {where}.rule_id is required.")
        if "*" in rule_id:
            raise ConfigError(
                f"--quality-policy: {where}.rule_id {rule_id!r}: wildcard rule IDs are not supported; "
                f"name one rule ID per exception.",
            )
        if rule_id not in KNOWN_RULE_IDS:
            raise ConfigError(
                f"--quality-policy: {where} has unknown rule_id {rule_id!r}. Allowed: {sorted(KNOWN_RULE_IDS)}.",
            )
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(f"--quality-policy: {where}.reason is required and must be a non-empty string.")
        has_id = "component_id" in item
        has_type = "component_type" in item
        if has_id == has_type:
            raise ConfigError(f"--quality-policy: {where} must set exactly one of component_id or component_type.")
        component_id: str | None = None
        component_type: str | None = None
        if has_id:
            component_id = item["component_id"]
            if not isinstance(component_id, str) or not component_id:
                raise ConfigError(f"--quality-policy: {where}.component_id must be a non-empty string.")
        else:
            raw_type = item["component_type"]
            component_type = raw_type.replace("-", "_") if isinstance(raw_type, str) else raw_type
            if component_type not in COMPONENT_FAMILIES:
                raise ConfigError(
                    f"--quality-policy: {where}.component_type must be one of {list(COMPONENT_FAMILIES)}, "
                    f"got {raw_type!r}.",
                )
        key = (rule_id, component_id, component_type)
        if key in seen:
            target = f"component_id {component_id!r}" if component_id else f"component_type {component_type!r}"
            raise ConfigError(f"--quality-policy: {where} is a duplicate exception for {rule_id} on {target}.")
        seen.add(key)
        out.append(
            QualityException(
                rule_id=rule_id,
                reason=reason.strip(),
                component_id=component_id,
                component_type=component_type,
            ),
        )
    return tuple(out)


def load_policy(path: Path) -> QualityPolicy:
    """Load a JSON policy file.

    Raises ConfigError on: file-not-found, JSON parse failure, unknown
    top-level keys (incl. dropped `max_issues` / `allow_partial`), invalid
    enum values, or a malformed `naming` / `exceptions` section.
    """
    if not path.exists():
        raise ConfigError(f"--quality-policy file not found: {path}")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"--quality-policy: failed to parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"--quality-policy: expected JSON object at top level, got {type(raw).__name__}",
        )

    # Unwrap envelope if present.
    if "quality_policy" in raw and isinstance(raw["quality_policy"], dict):
        raw = raw["quality_policy"]
    elif "quality" in raw and isinstance(raw["quality"], dict):
        raw = raw["quality"]

    # Canonicalize hyphen -> underscore.
    canon: dict[str, Any] = {}
    for k, v in raw.items():
        canon[k.replace("-", "_")] = v

    # Reject dropped keys with the explicit name in the message.
    for dropped in _DROPPED_KEYS:
        if dropped in canon:
            raise ConfigError(
                f"--quality-policy: key '{dropped}' is not supported in aa_auto_sdr "
                f"(dropped from cja's policy schema; see CHANGELOG v1.12.0).",
            )

    # Reject anything else we don't know.
    unknown = set(canon) - _KNOWN_KEYS
    if unknown:
        raise ConfigError(
            f"--quality-policy: unknown top-level key(s): {sorted(unknown)}. Allowed: {sorted(_KNOWN_KEYS)}.",
        )

    fail_on_quality: SeverityLevel | None = None
    if "fail_on_quality" in canon:
        val = canon["fail_on_quality"]
        # Case-insensitive, matching cja_auto_sdr.
        norm = val.strip().upper() if isinstance(val, str) else None
        if norm not in SeverityLevel.__members__:
            raise ConfigError(
                f"--quality-policy: fail_on_quality severity must be one of "
                f"{list(SeverityLevel.__members__)}, got {val!r}.",
            )
        fail_on_quality = SeverityLevel(norm)

    quality_report: Literal["json", "csv"] | None = None
    if "quality_report" in canon:
        val = canon["quality_report"]
        if val not in _VALID_REPORT_FORMATS:
            raise ConfigError(
                f"--quality-policy: quality_report format must be json|csv, got {val!r}.",
            )
        quality_report = val

    naming = _parse_naming(canon["naming"]) if "naming" in canon else {}
    exceptions = _parse_exceptions(canon["exceptions"]) if "exceptions" in canon else ()

    return QualityPolicy(
        fail_on_quality=fail_on_quality,
        quality_report=quality_report,
        naming=naming,
        exceptions=exceptions,
    )


def apply_policy_defaults(
    *,
    cli_namespace: argparse.Namespace,
    policy: QualityPolicy,
    explicitly_set: set[str],
) -> argparse.Namespace:
    """Mutate the namespace: fill unset fields from policy. CLI always wins.

    `explicitly_set` is the set of namespace attribute names the user passed
    on the command line. Built in cli/main.py by inspecting sys.argv before
    argparse runs (or by tracking via a custom Action).
    """
    if (
        "fail_on_quality" not in explicitly_set
        and getattr(cli_namespace, "fail_on_quality", None) is None
        and policy.fail_on_quality is not None
    ):
        cli_namespace.fail_on_quality = policy.fail_on_quality.value
    if (
        "quality_report" not in explicitly_set
        and getattr(cli_namespace, "quality_report", None) is None
        and policy.quality_report is not None
    ):
        cli_namespace.quality_report = policy.quality_report
    return cli_namespace


def write_quality_report(
    *,
    issues: list[Issue],
    summary: dict[str, Any],
    target: Path | str,  # str only for the special "-" stdout sentinel
    fmt: Literal["json", "csv"],
) -> None:
    """Emit the standalone quality report.

    JSON: {issues, summary}. CSV: header + one row per issue.
    Writes to stdout when target is "-", else to the file path.
    """
    if fmt == "json":
        payload = {
            "issues": [i.to_dict() for i in issues],
            "summary": summary,
        }
        rendered = json.dumps(payload, sort_keys=True, indent=2) + "\n"
        if target == "-":
            sys.stdout.write(rendered)
        else:
            atomic_write_text(Path(target), rendered)
        return

    if fmt == "csv":
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(_REPORT_CSV_HEADERS)
        for i in issues:
            d = i.to_dict()
            writer.writerow(
                [
                    d["severity"],
                    d["category"],
                    d["type"],
                    d["item_id"],
                    d["item_name"],
                    d["issue"],
                    d["rule_id"],
                    ", ".join(d["component_ids"]),
                    d["occurrences"],
                    "true" if d["excepted"] else "false",
                    d["exception_reason"] or "",
                ],
            )
        rendered = buf.getvalue()
        if target == "-":
            sys.stdout.write(rendered)
        else:
            # Python's csv.writer emits "\r\n" terminators by design. On Windows,
            # write_text()'s default universal-newline translation would convert
            # the "\n" to "\r\n" again, producing "\r\r\n" in the file and a
            # spurious empty line between every row. newline="" disables the
            # translation and matches the standard csv-on-Windows recipe.
            atomic_write_text(Path(target), rendered, newline="")
        return

    raise ConfigError(f"unsupported quality-report format: {fmt}")
