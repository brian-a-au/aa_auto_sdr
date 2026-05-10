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
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.sdr.quality import Issue, SeverityLevel

_VALID_REPORT_FORMATS = ("json", "csv")
_KNOWN_KEYS = {"fail_on_quality", "quality_report"}
_DROPPED_KEYS = {"max_issues", "allow_partial"}


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    fail_on_quality: SeverityLevel | None = None
    quality_report: Literal["json", "csv"] | None = None


def load_policy(path: Path) -> QualityPolicy:
    """Load a JSON policy file.

    Raises ConfigError on: file-not-found, JSON parse failure, unknown
    top-level keys (incl. dropped `max_issues` / `allow_partial`), or
    invalid enum values.
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
        if not isinstance(val, str) or val not in SeverityLevel.__members__:
            raise ConfigError(
                f"--quality-policy: fail_on_quality severity must be one of "
                f"{list(SeverityLevel.__members__)}, got {val!r}.",
            )
        fail_on_quality = SeverityLevel(val)

    quality_report: Literal["json", "csv"] | None = None
    if "quality_report" in canon:
        val = canon["quality_report"]
        if val not in _VALID_REPORT_FORMATS:
            raise ConfigError(
                f"--quality-policy: quality_report format must be json|csv, got {val!r}.",
            )
        quality_report = val

    return QualityPolicy(fail_on_quality=fail_on_quality, quality_report=quality_report)


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
            Path(target).write_text(rendered)
        return

    if fmt == "csv":
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["severity", "category", "type", "item_id", "item_name", "issue"])
        for i in issues:
            writer.writerow([i.severity.value, i.category, i.type, i.item_id, i.item_name, i.issue])
        rendered = buf.getvalue()
        if target == "-":
            sys.stdout.write(rendered)
        else:
            # Python's csv.writer emits "\r\n" terminators by design. On Windows,
            # write_text()'s default universal-newline translation would convert
            # the "\n" to "\r\n" again, producing "\r\r\n" in the file and a
            # spurious empty line between every row. newline="" disables the
            # translation and matches the standard csv-on-Windows recipe.
            Path(target).write_text(rendered, newline="")
        return

    raise ConfigError(f"unsupported quality-report format: {fmt}")
