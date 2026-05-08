"""Meta-test: every client.handle.<verb>(...) call in api/fetch.py must be
wrapped in either with_retries(...) or _retry_and_normalize(...) — both are
acceptable wrappers because _retry_and_normalize internally delegates to
with_retries.

Pattern enforced (one of):
    with_retries(lambda: client.handle.X(...), policy=..., on_attempt=...)
    _retry_and_normalize(lambda: client.handle.X(...), policy=..., ...)

A bare `client.handle.X(...)` outside either wrapper is a regression —
retries don't reach it. This mirrors the read-only-contract meta-test in
tests/api/test_read_only_contract.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

FETCH_PATH = Path(__file__).parent.parent.parent / "src" / "aa_auto_sdr" / "api" / "fetch.py"

_WRAPPER_NAMES = frozenset({"with_retries", "_retry_and_normalize"})


def _is_handle_attr_call(node: ast.AST) -> bool:
    """True if node is `client.handle.<anything>(...)`."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    inner = func.value
    if not isinstance(inner, ast.Attribute):
        return False
    return isinstance(inner.value, ast.Name) and inner.attr == "handle"


def _is_wrapper_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _WRAPPER_NAMES


def test_every_handle_call_is_wrapped() -> None:
    src = FETCH_PATH.read_text()
    tree = ast.parse(src)

    # Collect all wrapper call nodes; gather every handle-call inside any of
    # their argument subtrees; assert the union equals the full set of handle
    # calls in the module. (ast.walk doesn't track parents, so this
    # subtree-membership approach is simpler than a parent map.)
    all_handle_calls = [n for n in ast.walk(tree) if _is_handle_attr_call(n)]
    wrapped_handle_calls: set[int] = set()
    for node in ast.walk(tree):
        if _is_wrapper_call(node):
            for child in ast.walk(node):
                if _is_handle_attr_call(child):
                    wrapped_handle_calls.add(id(child))
    unwrapped = [(n.lineno, ast.unparse(n)[:80]) for n in all_handle_calls if id(n) not in wrapped_handle_calls]
    assert not unwrapped, (
        f"{len(unwrapped)} client.handle.* calls in api/fetch.py are not wrapped "
        f"in with_retries or _retry_and_normalize:\n" + "\n".join(f"  L{ln}: {src}" for ln, src in unwrapped)
    )


def test_retry_and_normalize_definition_uses_with_retries() -> None:
    """Defense: _retry_and_normalize must internally delegate to with_retries.
    Without this, a future refactor could rename the internal call and the
    meta-test above would silently accept bypassed retry logic."""
    src = FETCH_PATH.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_retry_and_normalize":
            inner_calls = [
                c
                for c in ast.walk(node)
                if _is_wrapper_call(c) and isinstance(c.func, ast.Name) and c.func.id == "with_retries"
            ]
            assert inner_calls, "_retry_and_normalize must call with_retries internally"
            return
    raise AssertionError("_retry_and_normalize function not found in api/fetch.py")
