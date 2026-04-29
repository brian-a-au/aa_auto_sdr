"""v1.4 meta-test — the four target modules' logger.* calls must use the
structured-fields vocabulary defined in docs/LOGGING_STYLE.md (spec §6.2).

Drift the meta-test catches:
- Message text mentions a vocabulary keyword but `extra={...}` doesn't carry
  the corresponding key.
- `extra={...}` carries a key not in the canonical vocabulary.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

VOCAB = {
    "rsid",
    "component_type",
    "count",
    "duration_ms",
    "output_path",
    "format",
    "snapshot_id",
    "batch_id",
    "error_class",
    "retry_attempt",
    "company_id",
    "company_id_source",
    "client_id_prefix",
    "reason",
    "exit_code",
    "count_failed",
    "argv_summary",
    "run_mode",
}
# `format` is also a Python builtin, so we treat it as vocab only when it
# appears as a `key=` token in a message string, not as a substring.

TARGET_MODULES = [
    Path("src/aa_auto_sdr/api/client.py"),
    Path("src/aa_auto_sdr/cli/main.py"),
    Path("src/aa_auto_sdr/pipeline/batch.py"),
    Path("src/aa_auto_sdr/snapshot/store.py"),
]


def _logger_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)):
            continue
        if f.value.id != "logger":
            continue
        if f.attr not in {"debug", "info", "warning", "error", "critical", "exception"}:
            continue
        yield node


def _extras_dict(call: ast.Call) -> dict[str, ast.AST] | None:
    for kw in call.keywords:
        if kw.arg == "extra" and isinstance(kw.value, ast.Dict):
            return {
                k.value: v
                for k, v in zip(kw.value.keys, kw.value.values, strict=False)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    return None


def _message_string(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


@pytest.mark.parametrize("module_path", TARGET_MODULES, ids=lambda p: p.name)
def test_logger_calls_use_canonical_vocabulary(module_path):
    src = module_path.read_text()
    tree = ast.parse(src)
    for call in _logger_calls(tree):
        msg = _message_string(call)
        extras = _extras_dict(call) or {}
        # Rule 1: extras keys must all be in the vocabulary.
        unknown = set(extras) - VOCAB
        assert not unknown, (
            f"{module_path}: logger call uses extras keys not in canonical "
            f"vocabulary: {unknown}. Add to docs/LOGGING_STYLE.md §6.2 first, "
            f"then to the VOCAB set in this test."
        )
        # Rule 2: if message contains `key=` for a vocabulary key, that key
        # must be in extras. (Substring match `key=` is safer than bare
        # substring — avoids false positives on words like 'format' inside
        # other text.)
        if msg is None:
            continue
        for key in VOCAB:
            if f"{key}=" in msg and key not in extras:
                pytest.fail(
                    f"{module_path}: logger call message mentions "
                    f"`{key}=` but `extra={{}}` does not carry the key. "
                    f"Message: {msg!r}"
                )
