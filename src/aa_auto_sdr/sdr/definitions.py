"""Readable summaries of calculated-metric and segment definitions, and the
references appendix (what each component references and what references it).

Pure: takes definitions (plain JSON-shaped dicts) or an SdrDocument, returns
strings, tuples, and plain dicts. No I/O, no heavy imports.

The summarizer understands a deliberately small part of the Adobe Analytics
2.0 definition grammar. Anything outside it is shown raw as
`[unparsed: <func>]` instead of being guessed at, so a summary never claims
more than the definition says. The full definition JSON stays in every
output; the summary is a reading aid.

Calculated metrics (`definition.formula`):

- `metric` (`name`) renders as the metric ID; `number` (`val`) as the literal.
- `add`, `subtract`, `multiply`, `divide` (`col1`, `col2`) render as
  `+ - * /` with operand order preserved. Parentheses follow precedence:
  `* /` bind tighter than `+ -`, and a right operand of equal precedence is
  parenthesized unless the chain is the same associative operator.
- `negate` (`col`) renders as a leading `-`.
- `abs`, `round`, `ceil`, `floor` (`col`) render as `ABS(...)` and so on.
- `segment` (`segment_id`, `metric`) renders as `<metric>[segment <id>]`.

Segments (`definition.container`):

- `container` with `context` `hits` / `visits` / `visitors` renders as
  `Hit where ...` / `Visit where ...` / `Visitor where ...`; a nested
  container is wrapped in parentheses.
- `and` / `or` (`preds`) render as `AND` / `OR`. A child of the other
  operator is parenthesized; a child of the same operator is not.
- `not` (`pred`) renders as `NOT (...)`; `without` (`pred`) as `EXCLUDE (...)`.
- Comparisons on an `attr` or `event` subject (`val`): `streq` `=`,
  `not-streq` `!=`, `contains`, `not-contains`, `starts-with`,
  `not-starts-with`, `ends-with`, `not-ends-with` (string `str`); `eq` `=`,
  `ne` `!=`, `gt` `>`, `lt` `<`, `ge` `>=`, `le` `<=` (number `num`);
  `exists` / `not-exists`; `event-exists` / `not-event-exists` (`evt`).
- `segment` (`segment_id`) renders as `segment <id>`.

Limits: recursion stops at `MAX_DEPTH` levels (the subtree below shows
`[unparsed: depth limit]`), and a definition with more than `MAX_NODES`
nodes is summarized as `[unparsed: definition exceeds N nodes]`. Reference
extraction walks the raw JSON iteratively, so it also finds IDs inside
unparsed nodes; it visits at most `MAX_WALK_NODES` nodes, `MAX_WALK_DEPTH`
levels deep, and never revisits the same object. The references appendix
lists direct references only, so reference cycles between components
(segment A uses B, B uses A) are listed as two edges and never followed."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

MAX_DEPTH = 64
MAX_NODES = 1000
MAX_WALK_NODES = 50_000
MAX_WALK_DEPTH = 256

# New output columns per component family, in output order.
DERIVED_COLUMNS: dict[str, tuple[str, ...]] = {
    "calculated_metrics": ("formula_summary", "metric_references", "segment_references"),
    "segments": ("definition_summary", "metric_references", "segment_references"),
}

REFERENCE_FAMILIES: tuple[str, ...] = ("calculated_metrics", "segments", "virtual_report_suites")

REFERENCE_COLUMNS: tuple[str, ...] = (
    "family",
    "id",
    "name",
    "relation",
    "kind",
    "target_family",
    "target_id",
    "target_name",
    "status",
)


class _TooLarge(Exception):
    pass


class _Budget:
    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 0

    def tick(self) -> None:
        self.count += 1
        if self.count > MAX_NODES:
            raise _TooLarge


def _unparsed(label: str) -> str:
    return f"[unparsed: {label}]"


def _func(node: dict[str, Any]) -> str | None:
    func = node.get("func")
    return func if isinstance(func, str) and func else None


def _nonempty_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _summarize(definition: Any, key: str, render: Any) -> str:
    if isinstance(definition, dict) and not definition:
        return ""
    if not isinstance(definition, dict) or key not in definition:
        return _unparsed("definition")
    try:
        return render(definition[key], _Budget())
    except _TooLarge:
        return _unparsed(f"definition exceeds {MAX_NODES} nodes")
    except Exception:  # a summary must never break a report
        return _unparsed("definition")


# --- calculated metric formulas ---------------------------------------------

_ADD, _MUL, _UNARY, _ATOM = 1, 2, 3, 4
_BINARY: dict[str, tuple[str, int]] = {
    "add": ("+", _ADD),
    "subtract": ("-", _ADD),
    "multiply": ("*", _MUL),
    "divide": ("/", _MUL),
}
_ASSOCIATIVE = ("add", "multiply")
_FUNCTIONS = ("abs", "round", "ceil", "floor")


def summarize_formula(definition: Any) -> str:
    """One-line arithmetic summary of a calculated metric's `definition`."""
    return _summarize(definition, "formula", lambda node, budget: _formula(node, 1, budget)[0])


def _formula(node: Any, depth: int, budget: _Budget) -> tuple[str, int, str | None]:
    """Return (text, precedence, binary operator func or None)."""
    if depth > MAX_DEPTH:
        return _unparsed("depth limit"), _ATOM, None
    budget.tick()
    if not isinstance(node, dict):
        return _unparsed(type(node).__name__), _ATOM, None
    func = _func(node)
    if func is None:
        return _unparsed("node"), _ATOM, None
    raw = _unparsed(func), _ATOM, None

    if func == "metric":
        name = _nonempty_str(node.get("name"))
        return (name, _ATOM, None) if name else raw
    if func == "number":
        value = _number(node.get("val"))
        if value is None:
            return raw
        return repr(value), (_UNARY if value < 0 else _ATOM), None
    if func in _BINARY:
        if "col1" not in node or "col2" not in node:
            return raw
        symbol, prec = _BINARY[func]
        left, left_prec, _ = _formula(node["col1"], depth + 1, budget)
        right, right_prec, right_op = _formula(node["col2"], depth + 1, budget)
        if left_prec < prec:
            left = f"({left})"
        if right_prec < prec or (right_prec == prec and not (right_op == func and func in _ASSOCIATIVE)):
            right = f"({right})"
        return f"{left} {symbol} {right}", prec, func
    if func == "negate":
        if "col" not in node:
            return raw
        inner, inner_prec, _ = _formula(node["col"], depth + 1, budget)
        return (f"-({inner})" if inner_prec <= _UNARY else f"-{inner}"), _UNARY, None
    if func in _FUNCTIONS:
        if "col" not in node:
            return raw
        inner, _, _ = _formula(node["col"], depth + 1, budget)
        return f"{func.upper()}({inner})", _ATOM, None
    if func == "segment":
        segment_id = _nonempty_str(node.get("segment_id"))
        if segment_id is None or "metric" not in node:
            return raw
        inner, inner_prec, _ = _formula(node["metric"], depth + 1, budget)
        if inner_prec < _ATOM:
            inner = f"({inner})"
        return f"{inner}[segment {segment_id}]", _ATOM, None
    return raw


# --- segment definitions -----------------------------------------------------

_CONTEXTS = {"hits": "Hit", "visits": "Visit", "visitors": "Visitor"}
_STRING_OPS = {
    "streq": "=",
    "not-streq": "!=",
    "contains": "contains",
    "not-contains": "does not contain",
    "starts-with": "starts with",
    "not-starts-with": "does not start with",
    "ends-with": "ends with",
    "not-ends-with": "does not end with",
}
_NUMBER_OPS = {"eq": "=", "ne": "!=", "gt": ">", "lt": "<", "ge": ">=", "le": "<="}
_EXISTS_OPS = {"exists": "exists", "not-exists": "does not exist"}
_EVENT_EXISTS_OPS = {"event-exists": "exists", "not-event-exists": "does not exist"}
_LOGIC = {"and": "AND", "or": "OR"}


def summarize_segment(definition: Any) -> str:
    """One-line logical summary of a segment's `definition`."""
    return _summarize(definition, "container", lambda node, budget: _container(node, 1, budget))


def _quote(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _subject(value: Any) -> str | None:
    if isinstance(value, dict) and _func(value) in ("attr", "event"):
        return _nonempty_str(value.get("name"))
    return None


def _container(node: Any, depth: int, budget: _Budget) -> str:
    if depth > MAX_DEPTH:
        return _unparsed("depth limit")
    budget.tick()
    if not isinstance(node, dict):
        return _unparsed(type(node).__name__)
    context = node.get("context")
    word = _CONTEXTS.get(context) if isinstance(context, str) else None
    if _func(node) != "container" or word is None or "pred" not in node:
        return _unparsed("container")
    text, _ = _pred(node["pred"], depth + 1, budget)
    return f"{word} where {text}"


def _pred(node: Any, depth: int, budget: _Budget) -> tuple[str, str | None]:
    """Return (text, logic operator func or None)."""
    if depth > MAX_DEPTH:
        return _unparsed("depth limit"), None
    if not isinstance(node, dict):
        budget.tick()
        return _unparsed(type(node).__name__), None
    func = _func(node)
    if func == "container":
        text = _container(node, depth, budget)
        return (text if text.startswith("[unparsed:") else f"({text})"), None
    budget.tick()
    if func is None:
        return _unparsed("node"), None
    raw = _unparsed(func), None

    if func in _LOGIC:
        preds = node.get("preds")
        if not isinstance(preds, list) or not preds:
            return raw
        rendered = [_pred(child, depth + 1, budget) for child in preds]
        if len(rendered) == 1:
            return rendered[0]
        parts = [f"({text})" if op not in (None, func) else text for text, op in rendered]
        return f" {_LOGIC[func]} ".join(parts), func
    if func in ("not", "without"):
        inner = node.get("pred")
        if not isinstance(inner, dict):
            return raw
        # A container operand already reads as a unit; wrap it only once.
        if _func(inner) == "container":
            text = _container(inner, depth + 1, budget)
        else:
            text, _ = _pred(inner, depth + 1, budget)
        return f"{'NOT' if func == 'not' else 'EXCLUDE'} ({text})", None
    if func == "segment":
        segment_id = _nonempty_str(node.get("segment_id"))
        return (f"segment {segment_id}", None) if segment_id else raw
    if func in _EVENT_EXISTS_OPS:
        subject = _subject(node.get("evt"))
        return (f"{subject} {_EVENT_EXISTS_OPS[func]}", None) if subject else raw

    subject = _subject(node.get("val"))
    if subject is None:
        return raw
    if func in _EXISTS_OPS:
        return f"{subject} {_EXISTS_OPS[func]}", None
    if func in _STRING_OPS:
        value = node.get("str")
        if not isinstance(value, str):
            return raw
        return f"{subject} {_STRING_OPS[func]} {_quote(value)}", None
    if func in _NUMBER_OPS:
        number = _number(node.get("num"))
        if number is None:
            return raw
        return f"{subject} {_NUMBER_OPS[func]} {number!r}", None
    return raw


# --- references --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class References:
    """Sorted, unique IDs a definition names directly."""

    metrics: tuple[str, ...] = ()
    segments: tuple[str, ...] = ()


def extract_references(definition: Any) -> References:
    """Metric IDs (`metric` / `event` nodes' `name`) and segment IDs
    (`segment` nodes' `segment_id`) anywhere in the definition, including
    inside nodes the summarizer does not understand."""
    metrics: set[str] = set()
    segments: set[str] = set()
    seen: set[int] = set()
    stack: list[tuple[Any, int]] = [(definition, 0)]
    visited = 0
    while stack and visited < MAX_WALK_NODES:
        obj, depth = stack.pop()
        if not isinstance(obj, (dict, list)) or id(obj) in seen or depth > MAX_WALK_DEPTH:
            continue
        seen.add(id(obj))
        visited += 1
        if isinstance(obj, dict):
            func = obj.get("func")
            if func in ("metric", "event"):
                name = _nonempty_str(obj.get("name"))
                if name:
                    metrics.add(name)
            elif func == "segment":
                segment_id = _nonempty_str(obj.get("segment_id"))
                if segment_id:
                    segments.add(segment_id)
            children = obj.values()
        else:
            children = obj
        stack.extend((child, depth + 1) for child in children if isinstance(child, (dict, list)))
    return References(metrics=tuple(sorted(metrics)), segments=tuple(sorted(segments)))


def derived_fields(family: str, item: Any) -> dict[str, Any]:
    """The additive output fields for one component, keyed in
    `DERIVED_COLUMNS` order. Empty for families without definitions."""
    return _derived_for_definition(family, getattr(item, "definition", None))


def _derived_for_definition(family: str, definition: Any) -> dict[str, Any]:
    if family not in DERIVED_COLUMNS:
        return {}
    refs = extract_references(definition)
    summary_key = DERIVED_COLUMNS[family][0]
    summary = summarize_formula(definition) if family == "calculated_metrics" else summarize_segment(definition)
    return {
        summary_key: summary,
        "metric_references": list(refs.metrics),
        "segment_references": list(refs.segments),
    }


# --- references appendix -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReferenceTarget:
    """One thing a component references. `family`/`name` are None and
    `status` is `unresolved` when the ID is not in the capture."""

    kind: str  # "metric" or "segment"
    id: str
    family: str | None
    name: str | None
    status: str  # "resolved" or "unresolved"


@dataclass(frozen=True, slots=True)
class Referrer:
    family: str
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ReferenceEntry:
    family: str
    id: str
    name: str
    references: tuple[ReferenceTarget, ...]
    referenced_by: tuple[Referrer, ...]


def build_references(doc: Any) -> list[ReferenceEntry]:
    """One entry per calculated metric, segment, and virtual report suite,
    by family then ID, with direct references resolved against the capture."""
    metric_names = {m.id: m.name for m in doc.metrics}
    names: dict[str, dict[str, str]] = {
        "calculated_metrics": {c.id: c.name for c in doc.calculated_metrics},
        "segments": {s.id: s.name for s in doc.segments},
        "virtual_report_suites": {v.id: v.name for v in doc.virtual_report_suites},
    }

    def resolve_metric(mid: str) -> ReferenceTarget:
        if mid in names["calculated_metrics"]:
            return ReferenceTarget("metric", mid, "calculated_metrics", names["calculated_metrics"][mid], "resolved")
        if mid in metric_names:
            return ReferenceTarget("metric", mid, "metrics", metric_names[mid], "resolved")
        return ReferenceTarget("metric", mid, None, None, "unresolved")

    def resolve_segment(sid: str) -> ReferenceTarget:
        if sid in names["segments"]:
            return ReferenceTarget("segment", sid, "segments", names["segments"][sid], "resolved")
        return ReferenceTarget("segment", sid, None, None, "unresolved")

    raw: list[tuple[str, str, str, tuple[ReferenceTarget, ...]]] = []
    for family, items in (("calculated_metrics", doc.calculated_metrics), ("segments", doc.segments)):
        for item in sorted(items, key=lambda i: i.id):
            refs = extract_references(item.definition)
            targets = tuple(resolve_metric(x) for x in refs.metrics) + tuple(resolve_segment(x) for x in refs.segments)
            raw.append((family, item.id, item.name, targets))
    for vrs in sorted(doc.virtual_report_suites, key=lambda v: v.id):
        ids = sorted({s for s in vrs.segment_list if isinstance(s, str) and s})
        raw.append(("virtual_report_suites", vrs.id, vrs.name, tuple(resolve_segment(s) for s in ids)))

    referrers: dict[tuple[str, str], set[tuple[str, str, str]]] = {}
    for family, ident, name, targets in raw:
        for target in targets:
            if target.status == "resolved" and target.family in REFERENCE_FAMILIES:
                referrers.setdefault((target.family, target.id), set()).add((family, ident, name))

    return [
        ReferenceEntry(
            family=family,
            id=ident,
            name=name,
            references=targets,
            referenced_by=tuple(Referrer(*r) for r in sorted(referrers.get((family, ident), ()))),
        )
        for family, ident, name, targets in raw
    ]


def references_to_dict(entries: list[ReferenceEntry]) -> dict[str, list[dict[str, Any]]]:
    """JSON shape of the appendix: one list per family."""
    out: dict[str, list[dict[str, Any]]] = {family: [] for family in REFERENCE_FAMILIES}
    for e in entries:
        out[e.family].append(
            {
                "id": e.id,
                "name": e.name,
                "references": [
                    {"kind": t.kind, "id": t.id, "family": t.family, "name": t.name, "status": t.status}
                    for t in e.references
                ],
                "referenced_by": [{"family": r.family, "id": r.id, "name": r.name} for r in e.referenced_by],
            }
        )
    return out


def reference_rows(entries: list[ReferenceEntry]) -> list[tuple[str, ...]]:
    """Tabular shape of the appendix, one row per edge, in `REFERENCE_COLUMNS` order."""
    rows: list[tuple[str, ...]] = []
    for e in entries:
        rows.extend(
            (e.family, e.id, e.name, "references", t.kind, t.family or "", t.id, t.name or "", t.status)
            for t in e.references
        )
        rows.extend(
            (e.family, e.id, e.name, "referenced_by", "", r.family, r.id, r.name, "resolved") for r in e.referenced_by
        )
    return rows


def enrich_payload(doc: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """A copy of `doc.to_dict()` output with the derived fields on each
    calculated metric and segment, plus a top-level `references` block.

    The input is not mutated: snapshots keep using the plain payload, so
    the derived output never enters a snapshot or a diff."""
    out = dict(payload)
    for family in DERIVED_COLUMNS:
        rows = payload.get(family)
        if isinstance(rows, list):
            out[family] = [
                {**row, **_derived_for_definition(family, row.get("definition"))} if isinstance(row, dict) else row
                for row in rows
            ]
    out["references"] = references_to_dict(build_references(doc))
    return out
