"""Readable definition summaries and the references appendix (sdr/definitions.py)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr import definitions as d
from aa_auto_sdr.sdr.document import SdrDocument

FIXTURE = json.loads((Path(__file__).parent.parent / "fixtures" / "definitions" / "aa_definitions.json").read_text())


def m(name: str) -> dict[str, Any]:
    return {"func": "metric", "name": name}


def num(val: Any) -> dict[str, Any]:
    return {"func": "number", "val": val}


def op(func: str, a: Any, b: Any) -> dict[str, Any]:
    return {"func": func, "col1": a, "col2": b}


def cm(formula: Any) -> dict[str, Any]:
    return {"func": "calc-metric", "version": [1, 0, 0], "formula": formula}


def attr(name: str) -> dict[str, Any]:
    return {"func": "attr", "name": name}


def seg(pred: Any, context: str = "hits") -> dict[str, Any]:
    return {
        "func": "segment",
        "version": [1, 0, 0],
        "container": {"func": "container", "context": context, "pred": pred},
    }


def streq(name: str, value: str) -> dict[str, Any]:
    return {"func": "streq", "str": value, "val": attr(name)}


# --- calculated metric formulas ---------------------------------------------


class TestFormulaSummary:
    def test_realistic_divide(self) -> None:
        assert d.summarize_formula(FIXTURE["calculated_metrics"]["conversion_rate"]) == (
            "metrics/orders / metrics/visits"
        )

    @pytest.mark.parametrize(
        ("func", "symbol"),
        [("add", "+"), ("subtract", "-"), ("multiply", "*"), ("divide", "/")],
    )
    def test_binary_operators(self, func: str, symbol: str) -> None:
        assert d.summarize_formula(cm(op(func, m("metrics/a"), m("metrics/b")))) == f"metrics/a {symbol} metrics/b"

    def test_operand_order_is_preserved(self) -> None:
        assert d.summarize_formula(cm(op("subtract", m("metrics/b"), m("metrics/a")))) == "metrics/b - metrics/a"

    def test_number_literals(self) -> None:
        assert d.summarize_formula(cm(op("multiply", m("metrics/a"), num(100)))) == "metrics/a * 100"
        assert d.summarize_formula(cm(op("add", num(0.5), num(-2)))) == "0.5 + -2"

    def test_negate(self) -> None:
        assert d.summarize_formula(cm({"func": "negate", "col": m("metrics/a")})) == "-metrics/a"
        compound = {"func": "negate", "col": op("add", m("metrics/a"), m("metrics/b"))}
        assert d.summarize_formula(cm(compound)) == "-(metrics/a + metrics/b)"
        double = {"func": "negate", "col": {"func": "negate", "col": m("metrics/a")}}
        assert d.summarize_formula(cm(double)) == "-(-metrics/a)"

    @pytest.mark.parametrize("func", ["abs", "round", "ceil", "floor"])
    def test_unary_functions(self, func: str) -> None:
        node = {"func": func, "col": op("divide", m("metrics/a"), m("metrics/b"))}
        assert d.summarize_formula(cm(node)) == f"{func.upper()}(metrics/a / metrics/b)"

    def test_segment_applied_metric(self) -> None:
        node = {"func": "segment", "segment_id": "s_1", "metric": m("metrics/orders")}
        assert d.summarize_formula(cm(node)) == "metrics/orders[segment s_1]"

    def test_segment_applied_to_compound_metric_is_parenthesized(self) -> None:
        node = {"func": "segment", "segment_id": "s_1", "metric": op("add", m("metrics/a"), m("metrics/b"))}
        assert d.summarize_formula(cm(node)) == "(metrics/a + metrics/b)[segment s_1]"

    def test_lower_precedence_children_are_parenthesized(self) -> None:
        tree = op("multiply", op("add", m("metrics/a"), m("metrics/b")), m("metrics/c"))
        assert d.summarize_formula(cm(tree)) == "(metrics/a + metrics/b) * metrics/c"
        tree = op("divide", m("metrics/a"), op("subtract", m("metrics/b"), m("metrics/c")))
        assert d.summarize_formula(cm(tree)) == "metrics/a / (metrics/b - metrics/c)"

    def test_higher_precedence_children_are_not_parenthesized(self) -> None:
        tree = op("add", op("multiply", m("metrics/a"), m("metrics/b")), op("divide", m("metrics/c"), num(2)))
        assert d.summarize_formula(cm(tree)) == "metrics/a * metrics/b + metrics/c / 2"

    def test_same_precedence_right_operand_is_parenthesized_for_non_associative(self) -> None:
        assert (
            d.summarize_formula(cm(op("subtract", m("metrics/a"), op("subtract", m("metrics/b"), m("metrics/c")))))
            == "metrics/a - (metrics/b - metrics/c)"
        )
        assert (
            d.summarize_formula(cm(op("divide", m("metrics/a"), op("multiply", m("metrics/b"), m("metrics/c")))))
            == "metrics/a / (metrics/b * metrics/c)"
        )
        assert (
            d.summarize_formula(cm(op("add", m("metrics/a"), op("subtract", m("metrics/b"), m("metrics/c")))))
            == "metrics/a + (metrics/b - metrics/c)"
        )

    def test_same_operator_chains_left_and_associative_right_need_no_parens(self) -> None:
        left = op("subtract", op("subtract", m("metrics/a"), m("metrics/b")), m("metrics/c"))
        assert d.summarize_formula(cm(left)) == "metrics/a - metrics/b - metrics/c"
        right = op("add", m("metrics/a"), op("add", m("metrics/b"), m("metrics/c")))
        assert d.summarize_formula(cm(right)) == "metrics/a + metrics/b + metrics/c"

    def test_realistic_nested_formula(self) -> None:
        assert d.summarize_formula(FIXTURE["calculated_metrics"]["mobile_revenue_per_order_pct"]) == (
            "metrics/revenue[segment s300000_mobile] / (metrics/orders + 1) * 100"
        )

    def test_if_based_fixture_renders_as_if_call(self) -> None:
        assert d.summarize_formula(FIXTURE["calculated_metrics"]["if_based"]) == (
            "IF(metrics/visits > 0, cm300000_rate, 0)"
        )

    def test_if_with_bare_number_operands_as_returned_by_the_api(self) -> None:
        """Real AA 2.0 shape: `cond` comparison and `else` use bare numbers, not `number` nodes."""
        formula = {
            "func": "if",
            "cond": {"func": "le", "col1": m("metrics/occurrences"), "col2": 7},
            "then": m("metrics/occurrences"),
            "else": 0,
        }
        assert d.summarize_formula(cm(formula)) == "IF(metrics/occurrences <= 7, metrics/occurrences, 0)"

    @pytest.mark.parametrize(
        ("func", "symbol"),
        [("eq", "="), ("ne", "!="), ("gt", ">"), ("lt", "<"), ("ge", ">="), ("le", "<=")],
    )
    def test_comparison_operators(self, func: str, symbol: str) -> None:
        assert d.summarize_formula(cm(op(func, m("metrics/a"), num(2)))) == f"metrics/a {symbol} 2"

    def test_comparison_operands_keep_arithmetic_unparenthesized(self) -> None:
        tree = op("gt", op("add", m("metrics/a"), m("metrics/b")), num(1))
        assert d.summarize_formula(cm(tree)) == "metrics/a + metrics/b > 1"

    def test_arithmetic_on_a_comparison_parenthesizes_it(self) -> None:
        tree = op("multiply", op("gt", m("metrics/a"), num(0)), num(100))
        assert d.summarize_formula(cm(tree)) == "(metrics/a > 0) * 100"

    def test_bare_number_operand_renders_like_a_number_node(self) -> None:
        bare = d.summarize_formula(cm(op("subtract", m("metrics/a"), -2)))
        assert bare == d.summarize_formula(cm(op("subtract", m("metrics/a"), num(-2)))) == "metrics/a - -2"

    @pytest.mark.parametrize(
        "formula",
        [
            {"func": "if", "then": m("metrics/a"), "else": 0},
            {"func": "if", "cond": op("gt", m("metrics/a"), 0), "else": 0},
            {"func": "if", "cond": op("gt", m("metrics/a"), 0), "then": m("metrics/a")},
        ],
    )
    def test_if_missing_a_branch_is_unparsed(self, formula: dict[str, Any]) -> None:
        assert d.summarize_formula(cm(formula)) == "[unparsed: if]"

    @pytest.mark.parametrize("value", [True, float("inf"), float("nan")])
    def test_bare_non_finite_or_bool_operand_is_unparsed(self, value: Any) -> None:
        assert (
            d.summarize_formula(cm(op("add", m("metrics/a"), value)))
            == f"metrics/a + [unparsed: {type(value).__name__}]"
        )

    def test_unknown_function_is_visible_raw(self) -> None:
        tree = op("add", m("metrics/a"), {"func": "col-sum", "col": m("metrics/b")})
        assert d.summarize_formula(cm(tree)) == "metrics/a + [unparsed: col-sum]"

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ({"func": "divide", "col1": m("metrics/a")}, "[unparsed: divide]"),
            ({"func": "metric"}, "[unparsed: metric]"),
            ({"func": "metric", "name": 7}, "[unparsed: metric]"),
            ({"func": "number", "val": "ten"}, "[unparsed: number]"),
            ({"func": "number", "val": True}, "[unparsed: number]"),
            ({"func": "number", "val": float("nan")}, "[unparsed: number]"),
            ({"func": "segment", "metric": m("metrics/a")}, "[unparsed: segment]"),
            ({"func": "abs"}, "[unparsed: abs]"),
            ({"col1": m("metrics/a")}, "[unparsed: node]"),
            ("metrics/orders", "[unparsed: str]"),
            (None, "[unparsed: NoneType]"),
            ({"func": 12}, "[unparsed: node]"),
        ],
    )
    def test_malformed_nodes_degrade(self, node: Any, expected: str) -> None:
        assert d.summarize_formula(cm(node)) == expected

    @pytest.mark.parametrize(
        "definition",
        [None, "x", [], 3, {"func": "calc-metric"}, {"formula": None}],
    )
    def test_malformed_definitions_never_raise(self, definition: Any) -> None:
        assert d.summarize_formula(definition).startswith("[unparsed:")

    def test_empty_definition_is_blank(self) -> None:
        assert d.summarize_formula({}) == ""

    def test_legacy_args_shape_is_unparsed(self) -> None:
        legacy = {"formula": {"func": "divide", "args": ["metrics/orders", "metrics/visits"]}}
        assert d.summarize_formula(legacy) == "[unparsed: divide]"

    def test_deep_tree_hits_depth_limit_without_recursion_error(self) -> None:
        node: Any = m("metrics/a")
        for _ in range(5000):
            node = {"func": "negate", "col": node}
        out = d.summarize_formula(cm(node))
        assert "[unparsed: depth limit]" in out
        assert len(out) < 2000

    def test_large_tree_hits_size_limit(self) -> None:
        wide: Any = m("metrics/x")
        for _ in range(12):  # 2**12 leaves, shallow
            wide = op("add", wide, wide)
        assert d.summarize_formula(cm(wide)) == f"[unparsed: definition exceeds {d.MAX_NODES} nodes]"

    def test_self_referencing_dict_terminates(self) -> None:
        node: dict[str, Any] = {"func": "negate"}
        node["col"] = node
        out = d.summarize_formula(cm(node))
        assert "[unparsed: depth limit]" in out


# --- segment definitions -----------------------------------------------------


class TestSegmentSummary:
    def test_realistic_hit_container(self) -> None:
        assert d.summarize_segment(FIXTURE["segments"]["mobile_hits"]) == (
            "Hit where variables/mobiledevicetype = 'Mobile Phone'"
        )

    @pytest.mark.parametrize(("context", "word"), [("hits", "Hit"), ("visits", "Visit"), ("visitors", "Visitor")])
    def test_container_contexts(self, context: str, word: str) -> None:
        assert d.summarize_segment(seg(streq("variables/page", "Home"), context)) == (
            f"{word} where variables/page = 'Home'"
        )

    @pytest.mark.parametrize(
        ("pred", "expected"),
        [
            ({"func": "streq", "str": "a", "val": attr("v/x")}, "v/x = 'a'"),
            ({"func": "not-streq", "str": "a", "val": attr("v/x")}, "v/x != 'a'"),
            ({"func": "contains", "str": "a", "val": attr("v/x")}, "v/x contains 'a'"),
            ({"func": "not-contains", "str": "a", "val": attr("v/x")}, "v/x does not contain 'a'"),
            ({"func": "starts-with", "str": "a", "val": attr("v/x")}, "v/x starts with 'a'"),
            ({"func": "not-starts-with", "str": "a", "val": attr("v/x")}, "v/x does not start with 'a'"),
            ({"func": "ends-with", "str": "a", "val": attr("v/x")}, "v/x ends with 'a'"),
            ({"func": "not-ends-with", "str": "a", "val": attr("v/x")}, "v/x does not end with 'a'"),
            ({"func": "eq", "num": 1, "val": attr("v/x")}, "v/x = 1"),
            ({"func": "ne", "num": 1, "val": attr("v/x")}, "v/x != 1"),
            ({"func": "gt", "num": 1, "val": attr("v/x")}, "v/x > 1"),
            ({"func": "lt", "num": 1.5, "val": attr("v/x")}, "v/x < 1.5"),
            ({"func": "ge", "num": 1, "val": attr("v/x")}, "v/x >= 1"),
            ({"func": "le", "num": 1, "val": attr("v/x")}, "v/x <= 1"),
            ({"func": "exists", "val": attr("v/x")}, "v/x exists"),
            ({"func": "not-exists", "val": attr("v/x")}, "v/x does not exist"),
            ({"func": "event-exists", "evt": {"func": "event", "name": "metrics/orders"}}, "metrics/orders exists"),
            (
                {"func": "not-event-exists", "evt": {"func": "event", "name": "metrics/orders"}},
                "metrics/orders does not exist",
            ),
        ],
    )
    def test_comparisons(self, pred: dict[str, Any], expected: str) -> None:
        assert d.summarize_segment(seg(pred)) == f"Hit where {expected}"

    def test_string_values_are_quoted_and_escaped(self) -> None:
        assert d.summarize_segment(seg(streq("v/x", "it's a \\ test"))) == "Hit where v/x = 'it\\'s a \\\\ test'"

    def test_and_or_not_preserve_order(self) -> None:
        pred = {"func": "and", "preds": [streq("v/b", "2"), streq("v/a", "1")]}
        assert d.summarize_segment(seg(pred)) == "Hit where v/b = '2' AND v/a = '1'"
        pred = {"func": "or", "preds": [streq("v/b", "2"), streq("v/a", "1"), streq("v/c", "3")]}
        assert d.summarize_segment(seg(pred)) == "Hit where v/b = '2' OR v/a = '1' OR v/c = '3'"
        pred = {"func": "not", "pred": streq("v/a", "1")}
        assert d.summarize_segment(seg(pred)) == "Hit where NOT (v/a = '1')"

    def test_mixed_logic_is_parenthesized(self) -> None:
        pred = {
            "func": "or",
            "preds": [{"func": "and", "preds": [streq("v/a", "1"), streq("v/b", "2")]}, streq("v/c", "3")],
        }
        assert d.summarize_segment(seg(pred)) == "Hit where (v/a = '1' AND v/b = '2') OR v/c = '3'"
        pred = {
            "func": "and",
            "preds": [streq("v/a", "1"), {"func": "or", "preds": [streq("v/b", "2"), streq("v/c", "3")]}],
        }
        assert d.summarize_segment(seg(pred)) == "Hit where v/a = '1' AND (v/b = '2' OR v/c = '3')"

    def test_same_operator_nesting_is_flattened_without_parens(self) -> None:
        pred = {
            "func": "and",
            "preds": [streq("v/a", "1"), {"func": "and", "preds": [streq("v/b", "2"), streq("v/c", "3")]}],
        }
        assert d.summarize_segment(seg(pred)) == "Hit where v/a = '1' AND v/b = '2' AND v/c = '3'"

    def test_single_operand_logic(self) -> None:
        assert d.summarize_segment(seg({"func": "and", "preds": [streq("v/a", "1")]})) == "Hit where v/a = '1'"

    def test_realistic_nested_visit_with_exclude(self) -> None:
        assert d.summarize_segment(FIXTURE["segments"]["engaged_visits"]) == (
            "Visit where variables/pagedepth > 3 AND (variables/page contains 'pricing' OR metrics/orders exists)"
            " AND EXCLUDE (Hit where variables/evar5 = 'Internal')"
        )

    def test_nested_container_is_parenthesized(self) -> None:
        inner = {"func": "container", "context": "hits", "pred": streq("v/a", "1")}
        pred = {"func": "and", "preds": [inner, streq("v/b", "2")]}
        assert d.summarize_segment(seg(pred, "visitors")) == "Visitor where (Hit where v/a = '1') AND v/b = '2'"

    def test_segment_reference_inside_segment(self) -> None:
        pred = {"func": "and", "preds": [{"func": "segment", "segment_id": "s_other"}, streq("v/a", "1")]}
        assert d.summarize_segment(seg(pred)) == "Hit where segment s_other AND v/a = '1'"

    def test_definition_without_outer_func(self) -> None:
        definition = {
            "version": [1, 0, 0],
            "container": {"func": "container", "context": "hits", "pred": streq("v/a", "1")},
        }
        assert d.summarize_segment(definition) == "Hit where v/a = '1'"

    def test_unknown_nodes_are_visible_raw(self) -> None:
        assert d.summarize_segment(FIXTURE["segments"]["sequential"]) == "Visitor where [unparsed: sequence]"
        pred = {"func": "and", "preds": [streq("v/a", "1"), {"func": "within", "pred": streq("v/b", "x")}]}
        assert d.summarize_segment(seg(pred)) == "Hit where v/a = '1' AND [unparsed: within]"

    def test_streq_in_as_returned_by_the_api(self) -> None:
        pred = {
            "func": "streq-in",
            "list": ["Paid Search", "Display", "Social Campaigns"],
            "val": attr("variables/marketingchannel"),
        }
        assert d.summarize_segment(seg(pred, "visits")) == (
            "Visit where variables/marketingchannel in ('Paid Search', 'Display', 'Social Campaigns')"
        )

    def test_not_streq_in(self) -> None:
        pred = {"func": "not-streq-in", "list": ["a"], "val": attr("v/b")}
        assert d.summarize_segment(seg(pred)) == "Hit where v/b not in ('a')"

    def test_streq_in_long_list_is_capped(self) -> None:
        values = [f"v{i}" for i in range(d.MAX_LIST_ITEMS + 5)]
        out = d.summarize_segment(seg({"func": "streq-in", "list": values, "val": attr("v/b")}))
        assert out.endswith(f"'v{d.MAX_LIST_ITEMS - 1}', … +5 more)")

    @pytest.mark.parametrize("values", [[], "abc", ["a", 3], None])
    def test_streq_in_malformed_list_is_unparsed(self, values: Any) -> None:
        pred = {"func": "streq-in", "list": values, "val": attr("v/b")}
        assert d.summarize_segment(seg(pred)) == "Hit where [unparsed: streq-in]"

    def test_event_total_subject_as_returned_by_the_api(self) -> None:
        pred = {
            "func": "gt",
            "num": 10,
            "val": {"func": "total", "evt": {"func": "event", "name": "metrics/pageviews"}},
        }
        assert d.summarize_segment(seg(pred, "visits")) == "Visit where total(metrics/pageviews) > 10"

    @pytest.mark.parametrize(
        ("pred", "expected"),
        [
            ({"func": "streq", "val": attr("v/x")}, "[unparsed: streq]"),
            ({"func": "streq", "str": 3, "val": attr("v/x")}, "[unparsed: streq]"),
            ({"func": "gt", "num": "3", "val": attr("v/x")}, "[unparsed: gt]"),
            ({"func": "gt", "num": True, "val": attr("v/x")}, "[unparsed: gt]"),
            ({"func": "streq", "str": "a"}, "[unparsed: streq]"),
            ({"func": "streq", "str": "a", "val": {"func": "total", "evt": {}}}, "[unparsed: streq]"),
            ({"func": "exists"}, "[unparsed: exists]"),
            ({"func": "event-exists", "evt": {"func": "event"}}, "[unparsed: event-exists]"),
            ({"func": "and", "preds": []}, "[unparsed: and]"),
            ({"func": "or", "preds": "x"}, "[unparsed: or]"),
            ({"func": "not"}, "[unparsed: not]"),
            ({"func": "without", "pred": None}, "[unparsed: without]"),
            ({"func": "container", "context": "pages", "pred": streq("v/a", "1")}, "[unparsed: container]"),
            ({"func": "container", "context": "hits"}, "[unparsed: container]"),
            ({"func": "segment"}, "[unparsed: segment]"),
            ([], "[unparsed: list]"),
        ],
    )
    def test_malformed_predicates_degrade(self, pred: Any, expected: str) -> None:
        out = d.summarize_segment(seg(pred))
        assert expected in out

    @pytest.mark.parametrize(
        "definition",
        [None, "x", [], {"container": None}, {"container": {"func": "container", "context": 3, "pred": {}}}],
    )
    def test_malformed_definitions_never_raise(self, definition: Any) -> None:
        assert d.summarize_segment(definition).startswith("[unparsed:")

    def test_empty_definition_is_blank(self) -> None:
        assert d.summarize_segment({}) == ""

    def test_deep_nesting_hits_depth_limit(self) -> None:
        pred: Any = streq("v/a", "1")
        for _ in range(5000):
            pred = {"func": "not", "pred": pred}
        out = d.summarize_segment(seg(pred))
        assert "[unparsed: depth limit]" in out

    def test_wide_tree_hits_size_limit(self) -> None:
        pred = {"func": "or", "preds": [streq("v/a", str(i)) for i in range(d.MAX_NODES)]}
        assert d.summarize_segment(seg(pred)) == f"[unparsed: definition exceeds {d.MAX_NODES} nodes]"


# --- references --------------------------------------------------------------


class TestExtractReferences:
    def test_calculated_metric_refs_are_sorted_and_unique(self) -> None:
        refs = d.extract_references(FIXTURE["calculated_metrics"]["mobile_revenue_per_order_pct"])
        assert refs.metrics == ("metrics/orders", "metrics/revenue")
        assert refs.segments == ("s300000_mobile",)

    def test_refs_are_found_inside_unparsed_nodes(self) -> None:
        refs = d.extract_references(FIXTURE["calculated_metrics"]["if_based"])
        assert refs.metrics == ("cm300000_rate", "metrics/visits")

    def test_segment_refs(self) -> None:
        refs = d.extract_references(FIXTURE["segments"]["engaged_visits"])
        assert refs.metrics == ("metrics/orders",)
        assert refs.segments == ()
        nested = seg({"func": "segment", "segment_id": "s_b"})
        assert d.extract_references(nested).segments == ("s_b",)

    @pytest.mark.parametrize("definition", [None, "x", 3, [], {}, {"formula": [1, None, "metrics/a"]}])
    def test_malformed_definitions_yield_no_refs(self, definition: Any) -> None:
        refs = d.extract_references(definition)
        assert refs.metrics == ()
        assert refs.segments == ()

    def test_self_referencing_structure_terminates(self) -> None:
        node: dict[str, Any] = {"func": "add", "col1": m("metrics/a")}
        node["col2"] = node
        assert d.extract_references(cm(node)).metrics == ("metrics/a",)

    def test_deep_structure_terminates(self) -> None:
        node: Any = m("metrics/deep")
        for _ in range(100_000):
            node = {"func": "negate", "col": node}
        refs = d.extract_references(cm(node))  # bounded walk; no RecursionError
        assert refs.metrics == ()


class TestDerivedFields:
    def test_calculated_metric_fields(self) -> None:
        item = _cm("cm_1", "Rate", FIXTURE["calculated_metrics"]["conversion_rate"])
        assert d.derived_fields("calculated_metrics", item) == {
            "formula_summary": "metrics/orders / metrics/visits",
            "metric_references": ["metrics/orders", "metrics/visits"],
            "segment_references": [],
        }
        assert tuple(d.derived_fields("calculated_metrics", item)) == d.DERIVED_COLUMNS["calculated_metrics"]

    def test_segment_fields(self) -> None:
        item = _seg("s_1", "Mobile", FIXTURE["segments"]["mobile_hits"])
        assert d.derived_fields("segments", item) == {
            "definition_summary": "Hit where variables/mobiledevicetype = 'Mobile Phone'",
            "metric_references": [],
            "segment_references": [],
        }

    def test_other_families_have_none(self) -> None:
        assert d.derived_fields("dimensions", object()) == {}
        assert d.DERIVED_COLUMNS.get("virtual_report_suites") is None


# --- references appendix -----------------------------------------------------


def _cm(cid: str, name: str, definition: Any) -> models.CalculatedMetric:
    return models.CalculatedMetric(
        id=cid,
        name=name,
        description=None,
        rsid="rs",
        owner_id=None,
        polarity="positive",
        precision=0,
        type="decimal",
        definition=definition,
    )


def _seg(sid: str, name: str, definition: Any) -> models.Segment:
    return models.Segment(id=sid, name=name, description=None, rsid="rs", owner_id=None, definition=definition)


def _metric(mid: str, name: str) -> models.Metric:
    return models.Metric(id=mid, name=name, type="int", category=None, precision=0, segmentable=True, description=None)


def _vrs(vid: str, name: str, segments: list[str]) -> models.VirtualReportSuite:
    return models.VirtualReportSuite(
        id=vid, name=name, parent_rsid="rs", timezone=None, description=None, segment_list=segments
    )


def _doc(**families: Any) -> SdrDocument:
    base: dict[str, Any] = {
        "dimensions": [],
        "metrics": [],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
    }
    base.update(families)
    return SdrDocument(
        report_suite=models.ReportSuite(rsid="rs", name="RS", timezone=None, currency=None, parent_rsid=None),
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="1.0.0",
        **base,
    )


def _graph_doc() -> SdrDocument:
    """cm_rate -> metrics/orders, metrics/visits; cm_mobile -> cm_rate + s_mobile;
    s_mobile <-> s_loop (cycle); vrs_mobile -> s_mobile, s_gone (missing)."""
    return _doc(
        metrics=[_metric("metrics/orders", "Orders"), _metric("metrics/visits", "Visits")],
        calculated_metrics=[
            _cm("cm_rate", "Rate", cm(op("divide", m("metrics/orders"), m("metrics/visits")))),
            _cm(
                "cm_mobile",
                "Mobile Rate",
                cm({"func": "segment", "segment_id": "s_mobile", "metric": m("cm_rate")}),
            ),
            _cm("cm_orphan", "Orphan", cm(op("add", m("metrics/missing"), num(1)))),
        ],
        segments=[
            _seg(
                "s_mobile",
                "Mobile",
                seg({"func": "and", "preds": [streq("v/a", "1"), {"func": "segment", "segment_id": "s_loop"}]}),
            ),
            _seg("s_loop", "Loop", seg({"func": "segment", "segment_id": "s_mobile"})),
        ],
        virtual_report_suites=[_vrs("vrs_mobile", "Mobile VRS", ["s_mobile", "s_gone"])],
    )


class TestReferencesAppendix:
    def test_entries_cover_every_cm_segment_and_vrs_in_order(self) -> None:
        entries = d.build_references(_graph_doc())
        assert [(e.family, e.id) for e in entries] == [
            ("calculated_metrics", "cm_mobile"),
            ("calculated_metrics", "cm_orphan"),
            ("calculated_metrics", "cm_rate"),
            ("segments", "s_loop"),
            ("segments", "s_mobile"),
            ("virtual_report_suites", "vrs_mobile"),
        ]

    def test_references_are_resolved_against_the_capture(self) -> None:
        by_id = {e.id: e for e in d.build_references(_graph_doc())}
        rate = by_id["cm_rate"]
        assert [(r.kind, r.id, r.family, r.name, r.status) for r in rate.references] == [
            ("metric", "metrics/orders", "metrics", "Orders", "resolved"),
            ("metric", "metrics/visits", "metrics", "Visits", "resolved"),
        ]
        mobile = by_id["cm_mobile"]
        assert [(r.kind, r.id, r.family, r.status) for r in mobile.references] == [
            ("metric", "cm_rate", "calculated_metrics", "resolved"),
            ("segment", "s_mobile", "segments", "resolved"),
        ]

    def test_missing_references_are_unresolved_never_broken(self) -> None:
        by_id = {e.id: e for e in d.build_references(_graph_doc())}
        orphan = by_id["cm_orphan"].references
        assert [(r.id, r.family, r.name, r.status) for r in orphan] == [("metrics/missing", None, None, "unresolved")]
        vrs = by_id["vrs_mobile"].references
        assert [(r.id, r.status) for r in vrs] == [("s_gone", "unresolved"), ("s_mobile", "resolved")]
        flat = json.dumps(d.references_to_dict(d.build_references(_graph_doc())))
        assert "broken" not in flat

    def test_referenced_by(self) -> None:
        by_id = {e.id: e for e in d.build_references(_graph_doc())}
        assert [(r.family, r.id) for r in by_id["cm_rate"].referenced_by] == [("calculated_metrics", "cm_mobile")]
        assert [(r.family, r.id) for r in by_id["s_mobile"].referenced_by] == [
            ("calculated_metrics", "cm_mobile"),
            ("segments", "s_loop"),
            ("virtual_report_suites", "vrs_mobile"),
        ]
        assert [(r.family, r.id) for r in by_id["s_loop"].referenced_by] == [("segments", "s_mobile")]
        assert by_id["cm_orphan"].referenced_by == ()
        assert by_id["vrs_mobile"].referenced_by == ()

    def test_cycles_terminate_and_list_direct_edges_only(self) -> None:
        by_id = {e.id: e for e in d.build_references(_graph_doc())}
        assert [r.id for r in by_id["s_loop"].references] == ["s_mobile"]
        assert [r.id for r in by_id["s_mobile"].references] == ["s_loop"]

    def test_self_reference(self) -> None:
        doc = _doc(segments=[_seg("s_self", "Self", seg({"func": "segment", "segment_id": "s_self"}))])
        (entry,) = d.build_references(doc)
        assert [r.id for r in entry.references] == ["s_self"]
        assert [r.id for r in entry.referenced_by] == ["s_self"]

    def test_vrs_with_non_string_segment_entries(self) -> None:
        doc = _doc(virtual_report_suites=[_vrs("v", "V", ["s_a", 3, "", "s_a"])])  # type: ignore[list-item]
        (entry,) = d.build_references(doc)
        assert [r.id for r in entry.references] == ["s_a"]

    def test_empty_document(self) -> None:
        assert d.build_references(_doc()) == []
        assert d.references_to_dict([]) == {"calculated_metrics": [], "segments": [], "virtual_report_suites": []}
        assert d.reference_rows([]) == []

    def test_to_dict_shape(self) -> None:
        out = d.references_to_dict(d.build_references(_graph_doc()))
        assert list(out) == ["calculated_metrics", "segments", "virtual_report_suites"]
        assert out["calculated_metrics"][2] == {
            "id": "cm_rate",
            "name": "Rate",
            "references": [
                {"kind": "metric", "id": "metrics/orders", "family": "metrics", "name": "Orders", "status": "resolved"},
                {"kind": "metric", "id": "metrics/visits", "family": "metrics", "name": "Visits", "status": "resolved"},
            ],
            "referenced_by": [{"family": "calculated_metrics", "id": "cm_mobile", "name": "Mobile Rate"}],
        }

    def test_rows(self) -> None:
        rows = d.reference_rows(d.build_references(_graph_doc()))
        assert d.REFERENCE_COLUMNS == (
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
        assert rows[0] == (
            "calculated_metrics",
            "cm_mobile",
            "Mobile Rate",
            "references",
            "metric",
            "calculated_metrics",
            "cm_rate",
            "Rate",
            "resolved",
        )
        orphan = [r for r in rows if r[1] == "cm_orphan"]
        assert orphan == [
            (
                "calculated_metrics",
                "cm_orphan",
                "Orphan",
                "references",
                "metric",
                "",
                "metrics/missing",
                "",
                "unresolved",
            )
        ]
        rate_by = [r for r in rows if r[1] == "cm_rate" and r[3] == "referenced_by"]
        assert rate_by == [
            (
                "calculated_metrics",
                "cm_rate",
                "Rate",
                "referenced_by",
                "",
                "calculated_metrics",
                "cm_mobile",
                "Mobile Rate",
                "resolved",
            )
        ]


class TestEnrichPayload:
    def test_adds_fields_and_block_without_mutating_input(self) -> None:
        doc = _graph_doc()
        payload = doc.to_dict()
        before = json.dumps(payload, sort_keys=True)
        out = d.enrich_payload(doc, payload)
        assert json.dumps(payload, sort_keys=True) == before
        assert out["references"] == d.references_to_dict(d.build_references(doc))
        rate = next(c for c in out["calculated_metrics"] if c["id"] == "cm_rate")
        assert rate["formula_summary"] == "metrics/orders / metrics/visits"
        assert rate["metric_references"] == ["metrics/orders", "metrics/visits"]
        assert rate["definition"] == doc.calculated_metrics[0].definition
        loop = next(s for s in out["segments"] if s["id"] == "s_loop")
        assert loop["definition_summary"] == "Hit where segment s_mobile"
        assert loop["segment_references"] == ["s_mobile"]
        assert "formula_summary" not in out["virtual_report_suites"][0]


class TestReviewHardening:
    @pytest.mark.parametrize(
        ("ref_id", "cm_id"),
        [("metrics/cm300_rate", "cm300_rate"), ("cm300_rate", "metrics/cm300_rate")],
    )
    def test_nested_cm_resolves_with_or_without_metrics_prefix(self, ref_id: str, cm_id: str) -> None:
        doc = _doc(
            calculated_metrics=[
                _cm(cm_id, "Rate", cm(m("metrics/orders"))),
                _cm("cm_outer", "Outer", cm(op("multiply", m(ref_id), num(100)))),
            ]
        )
        by_id = {e.id: e for e in d.build_references(doc)}
        (target,) = by_id["cm_outer"].references
        assert (target.id, target.family, target.name, target.status) == (
            ref_id,
            "calculated_metrics",
            "Rate",
            "resolved",
        )
        assert [(r.family, r.id) for r in by_id[cm_id].referenced_by] == [("calculated_metrics", "cm_outer")]

    def test_exact_match_wins_over_prefix_variant(self) -> None:
        doc = _doc(
            metrics=[_metric("metrics/x", "Std X")],
            calculated_metrics=[_cm("x", "CM X", cm(num(1))), _cm("c", "C", cm(m("metrics/x")))],
        )
        by_id = {e.id: e for e in d.build_references(doc)}
        (target,) = by_id["c"].references
        assert (target.family, target.name) == ("metrics", "Std X")

    def test_quoted_values_are_one_line(self) -> None:
        out = d.summarize_segment(seg(streq("v/x", "a\nb\rc\td\x01e")))
        assert out == "Hit where v/x = 'a\\nb\\rc\\td\\x01e'"
        assert "\n" not in out
        assert d.summarize_segment(seg(streq("v/x", "a\u2028b\x7f"))) == "Hit where v/x = 'a\\u2028b\\x7f'"

    def test_long_quoted_values_are_capped(self) -> None:
        out = d.summarize_segment(seg(streq("v/x", "y" * 500)))
        assert out == "Hit where v/x = '" + "y" * d.MAX_QUOTED_CHARS + "…'"

    def test_integer_valued_floats_drop_the_point(self) -> None:
        assert d.summarize_formula(cm(op("multiply", m("metrics/a"), num(3.0)))) == "metrics/a * 3"
        assert d.summarize_formula(cm(num(2.5))) == "2.5"
        assert d.summarize_segment(seg({"func": "gt", "num": 1.0, "val": attr("v/x")})) == "Hit where v/x > 1"


class TestEdgeCases:
    def test_negate_without_operand(self) -> None:
        assert d.summarize_formula(cm({"func": "negate"})) == "[unparsed: negate]"

    def test_predicate_without_func(self) -> None:
        assert d.summarize_segment(seg({"str": "a"})) == "Hit where [unparsed: node]"

    def test_deeply_nested_containers_hit_depth_limit(self) -> None:
        container: Any = {"func": "container", "context": "hits", "pred": streq("v/a", "1")}
        for _ in range(200):
            container = {"func": "container", "context": "visits", "pred": container}
        out = d.summarize_segment({"container": container})
        assert "[unparsed: depth limit]" in out

    def test_unexpected_internal_error_degrades(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: Any) -> Any:
            raise ValueError("unexpected")

        monkeypatch.setattr(d, "_formula", boom)
        monkeypatch.setattr(d, "_container", boom)
        assert d.summarize_formula(cm(m("metrics/a"))) == "[unparsed: definition]"
        assert d.summarize_segment(seg(streq("v/a", "1"))) == "[unparsed: definition]"
