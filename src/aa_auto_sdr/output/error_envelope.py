"""JSON error envelope writer for pipe-path failures.

When `--output -` or `--format json` is in effect and an error occurs, write
a one-line JSON envelope to stderr while leaving stdout untouched (the
consumer's `jq` etc. sees empty input). See master design spec §6.2."""

from __future__ import annotations

import json
import sys

from aa_auto_sdr.core.exit_codes import EXPLANATIONS, ExitCode


def _hint_for(exit_code: int) -> str:
    """Extract a one-line hint from EXPLANATIONS[code] — the first non-blank line
    after a 'What to try:' header. Falls back to the empty string."""
    try:
        ec = ExitCode(exit_code)
    except ValueError:
        return ""
    text = EXPLANATIONS.get(ec, "")
    in_remediation = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("What to try:"):
            in_remediation = True
            continue
        if in_remediation and stripped.startswith("-"):
            return stripped.lstrip("-").strip()
    return ""


def emit_error_envelope(exc: BaseException, exit_code: int) -> None:
    """Write a one-line JSON error envelope to stderr."""
    payload = {
        "error": {
            "code": exit_code,
            "type": type(exc).__name__,
            "message": str(exc).replace("\n", " ").strip(),
            "hint": _hint_for(exit_code),
        },
    }
    sys.stderr.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stderr.flush()
