"""v1.5 meta-test — every instrumented module's logger.* calls must use the
structured-fields vocabulary defined in docs/LOGGING_STYLE.md (spec §6.1).

Drift the meta-test catches:
- Message text mentions a vocabulary keyword (as ``key=``) but ``extra={...}``
  doesn't carry the corresponding key.
- ``extra={...}`` carries a key not in the canonical vocabulary.
- A canonical event prefix appears in a message but the call site is missing
  the required extras for that event.

v1.5 changes vs v1.4:
- Reserved-events exemption dropped: ``component_fetch`` and ``output_write``
  are now ordinary canonical events with the same enforcement as the v1.4
  events (``run_start``, ``rsid_start``, etc.).
- Vocabulary expanded with ``component_type``, ``format``, ``command``,
  ``creds_source``, ``snapshot_spec`` (spec §6.1).
- Instrumented-modules enumeration extended from 4 → 26 to cover every
  module that emits ``logger.*`` calls in v1.5.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Canonical vocabulary — every key allowed in `extra={}` on a logger call.
# Keep in sync with docs/LOGGING_STYLE.md §"Structured fields vocabulary".
VOCAB = {
    # v1.4 carry-overs
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
    # v1.5 additions
    "command",
    "creds_source",
    "snapshot_spec",
    "tool_version",
    # v1.6 additions
    "agent_mode",
    # v1.7 additions
    "expansion_level",
    "pulled",
    "filtered",
    "dropped_no_parent",
    "dropped_other_parent",
}

# Canonical events whose presence in a message string mandates a fixed set of
# extras. Each entry: event prefix → required extras keys.
# (Per spec §6.2, v1.5 lifts the v1.4 reserved-events exemption — these are
# now ordinary canonical events with full keyword-extras enforcement.)
CANONICAL_EVENT_EXTRAS: dict[str, set[str]] = {
    "component_fetch": {"rsid", "component_type", "count", "duration_ms"},
    "output_write": {"format", "output_path", "count", "duration_ms", "rsid"},
    "command_start": {"command"},
    "command_complete": {"command", "exit_code", "duration_ms"},
    "creds_resolved": {"creds_source"},
    # v1.7.0 resilience-layer additions (per docs/LOGGING_STYLE.md
    # "Canonical event names" → v1.7.0 sub-block).
    "retry_attempt": {"retry_attempt", "error_class", "rsid", "component_type"},
    "vrs_expansion_fallback": {"rsid", "component_type", "expansion_level", "error_class"},
    "vrs_parent_filter": {"rsid", "pulled", "filtered", "dropped_no_parent", "dropped_other_parent"},
}

INSTRUMENTED_MODULES = [
    Path("src/aa_auto_sdr/api/client.py"),
    Path("src/aa_auto_sdr/api/fetch.py"),
    Path("src/aa_auto_sdr/cli/main.py"),
    Path("src/aa_auto_sdr/cli/commands/generate.py"),
    Path("src/aa_auto_sdr/cli/commands/batch.py"),
    Path("src/aa_auto_sdr/cli/commands/diff.py"),
    Path("src/aa_auto_sdr/cli/commands/discovery.py"),
    Path("src/aa_auto_sdr/cli/commands/inspect.py"),
    Path("src/aa_auto_sdr/cli/commands/snapshots.py"),
    Path("src/aa_auto_sdr/cli/commands/profiles.py"),
    Path("src/aa_auto_sdr/cli/commands/config.py"),
    Path("src/aa_auto_sdr/cli/commands/stats.py"),
    Path("src/aa_auto_sdr/cli/commands/interactive.py"),
    Path("src/aa_auto_sdr/core/credentials.py"),
    Path("src/aa_auto_sdr/core/profiles.py"),
    Path("src/aa_auto_sdr/output/writers/excel.py"),
    Path("src/aa_auto_sdr/output/writers/csv.py"),
    Path("src/aa_auto_sdr/output/writers/json.py"),
    Path("src/aa_auto_sdr/output/writers/html.py"),
    Path("src/aa_auto_sdr/output/writers/markdown.py"),
    Path("src/aa_auto_sdr/pipeline/batch.py"),
    Path("src/aa_auto_sdr/sdr/builder.py"),
    Path("src/aa_auto_sdr/snapshot/store.py"),
    Path("src/aa_auto_sdr/snapshot/comparator.py"),
    Path("src/aa_auto_sdr/snapshot/resolver.py"),
    Path("src/aa_auto_sdr/snapshot/git.py"),
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


@pytest.mark.parametrize("module_path", INSTRUMENTED_MODULES, ids=lambda p: p.name)
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
            f"vocabulary: {unknown}. Add to docs/LOGGING_STYLE.md §6.1 first, "
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


@pytest.mark.parametrize("module_path", INSTRUMENTED_MODULES, ids=lambda p: p.name)
def test_canonical_event_calls_carry_required_extras(module_path):
    """Every logger.* call whose message starts with a canonical event prefix
    must carry the full set of extras documented for that event in spec §6.2.

    Token-boundary-aware: matches the prefix only at message start followed by
    a space or end-of-string, so a comment-style substring (e.g. ``"see
    component_fetch in fetch.py"``) doesn't trigger.
    """
    src = module_path.read_text()
    tree = ast.parse(src)
    for call in _logger_calls(tree):
        msg = _message_string(call)
        if msg is None:
            continue
        extras = _extras_dict(call) or {}
        for prefix, required in CANONICAL_EVENT_EXTRAS.items():
            # Only match at the start of the message, followed by a space or
            # end-of-string. This is the canonical-event-prefix shape per
            # LOGGING_STYLE.md §message-style rules.
            if msg == prefix or msg.startswith(prefix + " "):
                missing = required - set(extras)
                assert not missing, (
                    f"{module_path}: logger call with canonical event "
                    f"prefix '{prefix}' is missing required extras: "
                    f"{sorted(missing)}. Required: {sorted(required)}. "
                    f"Got: {sorted(extras)}. Message: {msg!r}"
                )
