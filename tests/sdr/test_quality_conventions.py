"""Quality conventions: rule IDs, per-type naming rules, reasoned exceptions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.api.cache import ValidationCache
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.sdr.quality import (
    CUSTOM_RULE_ID,
    QUALITY_RULE_IDS,
    Issue,
    NamingRule,
    QualityException,
    QualityRules,
    SeverityLevel,
    matches_case_style,
    rule_id_for,
    run_audits,
)


def _dim(cid: str, name: str, **extra: Any) -> models.Dimension:
    return models.Dimension(
        id=cid,
        name=name,
        type="string",
        category=None,
        parent="",
        pathable=False,
        description=None,
        extra=dict(extra),
    )


def _metric(cid: str, name: str, **extra: Any) -> models.Metric:
    return models.Metric(
        id=cid,
        name=name,
        type="int",
        category=None,
        precision=0,
        segmentable=True,
        description=None,
        extra=dict(extra),
    )


def _doc(dims: list[Any] | None = None, metrics: list[Any] | None = None, vrs: list[Any] | None = None) -> SdrDocument:
    rs = models.ReportSuite(rsid="rs1", name="RS1", timezone=None, currency=None, parent_rsid=None)
    return SdrDocument(
        report_suite=rs,
        dimensions=dims or [],
        metrics=metrics or [],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=vrs or [],
        classifications=[],
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="test",
    )


def _issues(block: dict[str, Any], rule_id: str | None = None) -> list[dict[str, Any]]:
    return [i for i in block["issues"] if rule_id is None or i["rule_id"] == rule_id]


class TestRuleIds:
    def test_catalog(self) -> None:
        assert QUALITY_RULE_IDS == {
            "stale_keyword": "dq.stale_keyword.v1",
            "version_suffix": "dq.version_suffix.v1",
            "date_pattern": "dq.date_pattern.v1",
            "case_inconsistency": "dq.naming_case_inconsistency.v1",
            "naming_convention": "dq.naming_convention.v1",
        }
        assert CUSTOM_RULE_ID == "dq.custom.unknown"

    def test_unknown_type_falls_back(self) -> None:
        assert rule_id_for("mystery") == "dq.custom.unknown"

    def test_every_existing_finding_type_has_rule_id(self) -> None:
        doc = _doc(
            dims=[
                _dim("evar1", "page_test_2024-01-01_v2"),  # stale_keyword + version_suffix + date_pattern? (see below)
                _dim("evar2", "pageName"),
                _dim("evar3", "site_section"),
                _dim("evar4", "old_dim_20240101"),
            ],
        )
        block = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=True)
        by_type = {i["type"]: i["rule_id"] for i in block["issues"]}
        assert by_type["stale_keyword"] == "dq.stale_keyword.v1"
        assert by_type["version_suffix"] == "dq.version_suffix.v1"
        assert by_type["date_pattern"] == "dq.date_pattern.v1"
        assert by_type["case_inconsistency"] == "dq.naming_case_inconsistency.v1"
        for issue in block["issues"]:
            assert issue["rule_id"] != CUSTOM_RULE_ID
            assert issue["excepted"] is False
            assert issue["exception_reason"] is None

    def test_existing_keys_unchanged(self) -> None:
        issue = Issue(SeverityLevel.LOW, "stale", "version_suffix", "evar1", "x_v2", "msg", {"k": 1})
        d = issue.to_dict()
        for key in ("severity", "category", "type", "item_id", "item_name", "issue", "details"):
            assert key in d
        assert d["rule_id"] == "dq.version_suffix.v1"
        assert d["component_ids"] == []
        assert d["occurrences"] == 1


class TestComponentIdsAndOccurrences:
    def test_stale_finding_names_its_component(self) -> None:
        block = run_audits(
            _doc(dims=[_dim("evar9", "legacy_thing")]), audit_naming_enabled=False, flag_stale_enabled=True
        )
        (issue,) = block["issues"]
        assert issue["component_ids"] == ["evar9"]
        assert issue["occurrences"] == 1

    def test_case_inconsistency_lists_minority_components_sorted(self) -> None:
        doc = _doc(
            dims=[_dim("evar1", "page_name"), _dim("evar2", "site_section"), _dim("evar3", "zebraCase")],
            metrics=[_metric("event2", "orderCount"), _metric("event1", "cart_adds")],
        )
        block = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False)
        (issue,) = _issues(block, "dq.naming_case_inconsistency.v1")
        assert issue["component_ids"] == ["evar3", "event2"]
        assert issue["occurrences"] == 2


class TestCaseStyles:
    @pytest.mark.parametrize(
        ("style", "good", "bad"),
        [
            ("snake_case", ["page_name", "page", "page_name_2"], ["PageName", "page-name", "page__name", "_page"]),
            ("camelCase", ["pageName", "page", "pageURL"], ["PageName", "page_name", "page name"]),
            ("PascalCase", ["PageName", "Page", "PageURL"], ["pageName", "Page_Name", "Page Name"]),
            ("Title Case", ["Page Name", "Page", "Orders (Online)", "Top 10 Pages"], ["Page name", "page Name"]),
            ("kebab-case", ["page-name", "page", "page-name-2"], ["Page-Name", "page_name", "page--name"]),
            ("any", ["whatever You_Like", "x"], []),
        ],
    )
    def test_style(self, style: str, good: list[str], bad: list[str]) -> None:
        for name in good:
            assert matches_case_style(name, style), (style, name)
        for name in bad:
            assert not matches_case_style(name, style), (style, name)


class TestNamingConvention:
    def _rules(self, **naming: NamingRule) -> QualityRules:
        return QualityRules(naming=naming)

    def test_case_violation_flagged_low(self) -> None:
        doc = _doc(dims=[_dim("evar1", "page_name"), _dim("evar2", "PageName")])
        block = run_audits(
            doc,
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=self._rules(dimensions=NamingRule(case="snake_case")),
        )
        (issue,) = _issues(block, "dq.naming_convention.v1")
        assert issue["severity"] == "LOW"
        assert issue["category"] == "naming"
        assert issue["type"] == "naming_convention"
        assert issue["item_id"] == "evar2"
        assert issue["item_name"] == "PageName"
        assert issue["component_ids"] == ["evar2"]
        assert issue["occurrences"] == 1
        assert issue["details"]["component_type"] == "dimension"
        assert issue["details"]["expected_case"] == "snake_case"
        assert issue["details"]["violations"] == ["case"]

    def test_pattern_must_fully_match(self) -> None:
        doc = _doc(metrics=[_metric("event1", "kpi_orders"), _metric("event2", "orders_kpi_x")])
        block = run_audits(
            doc,
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=self._rules(metrics=NamingRule(pattern=r"kpi_[a-z]+")),
        )
        (issue,) = _issues(block, "dq.naming_convention.v1")
        assert issue["item_id"] == "event2"
        assert issue["details"]["pattern"] == "kpi_[a-z]+"
        assert issue["details"]["violations"] == ["pattern"]

    def test_case_and_pattern_combine_into_one_finding(self) -> None:
        doc = _doc(dims=[_dim("evar1", "Bad Name")])
        block = run_audits(
            doc,
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=self._rules(dimensions=NamingRule(case="snake_case", pattern=r"dim_.*")),
        )
        (issue,) = _issues(block, "dq.naming_convention.v1")
        assert issue["details"]["violations"] == ["case", "pattern"]

    def test_rules_scoped_to_their_family(self) -> None:
        doc = _doc(dims=[_dim("evar1", "PageName")], metrics=[_metric("event1", "OrderCount")])
        block = run_audits(
            doc,
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=self._rules(metrics=NamingRule(case="snake_case")),
        )
        assert [i["item_id"] for i in _issues(block, "dq.naming_convention.v1")] == ["event1"]

    def test_virtual_report_suites_evaluated_when_configured(self) -> None:
        vrs = models.VirtualReportSuite(
            id="vrs_x",
            name="Bad VRS",
            parent_rsid="rs1",
            timezone=None,
            description=None,
            segment_list=[],
            curated_components=[],
            modified=None,
        )
        block = run_audits(
            _doc(vrs=[vrs]),
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=self._rules(virtual_report_suites=NamingRule(case="kebab-case")),
        )
        assert [i["item_id"] for i in _issues(block, "dq.naming_convention.v1")] == ["vrs_x"]

    def test_standard_components_skipped_only_when_known(self) -> None:
        doc = _doc(
            dims=[
                _dim("variables/page", "Page", standardComponent=True),
                _dim("evar1", "Custom Thing", standardComponent=False),
                _dim("evar2", "Unknown Thing"),
            ],
        )
        block = run_audits(
            doc,
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=self._rules(dimensions=NamingRule(case="snake_case")),
        )
        assert sorted(i["item_id"] for i in _issues(block, "dq.naming_convention.v1")) == ["evar1", "evar2"]

    def test_not_evaluated_without_naming_audit(self) -> None:
        doc = _doc(dims=[_dim("evar1", "PageName")])
        block = run_audits(
            doc,
            audit_naming_enabled=False,
            flag_stale_enabled=True,
            rules=self._rules(dimensions=NamingRule(case="snake_case")),
        )
        assert _issues(block, "dq.naming_convention.v1") == []


class TestExceptions:
    def _doc(self) -> SdrDocument:
        return _doc(
            dims=[_dim("evar1", "legacy_page"), _dim("evar2", "old_section")],
            metrics=[_metric("event1", "legacy_orders")],
        )

    def test_component_id_exception(self) -> None:
        rules = QualityRules(
            exceptions=(
                QualityException(rule_id="dq.stale_keyword.v1", component_id="evar1", reason="kept for audit"),
            ),
        )
        block = run_audits(self._doc(), audit_naming_enabled=False, flag_stale_enabled=True, rules=rules)
        excepted = {i["item_id"]: i for i in block["issues"] if i["excepted"]}
        assert set(excepted) == {"evar1"}
        assert excepted["evar1"]["exception_reason"] == "kept for audit"
        assert block["summary"]["excepted"] == 1
        assert block["summary"]["total"] == 2
        assert sum(block["summary"]["by_severity"].values()) == 2
        assert len(block["issues"]) == 3  # excepted finding stays visible

    def test_component_type_exception(self) -> None:
        rules = QualityRules(
            exceptions=(
                QualityException(rule_id="dq.stale_keyword.v1", component_type="dimensions", reason="dims frozen"),
            ),
        )
        block = run_audits(self._doc(), audit_naming_enabled=False, flag_stale_enabled=True, rules=rules)
        assert sorted(i["item_id"] for i in block["issues"] if i["excepted"]) == ["evar1", "evar2"]
        assert block["summary"]["excepted"] == 2
        assert block["summary"]["total"] == 1

    def test_exception_only_matches_its_rule(self) -> None:
        rules = QualityRules(
            exceptions=(QualityException(rule_id="dq.version_suffix.v1", component_id="evar1", reason="n/a"),),
        )
        block = run_audits(self._doc(), audit_naming_enabled=False, flag_stale_enabled=True, rules=rules)
        assert not any(i["excepted"] for i in block["issues"])
        assert block["summary"]["excepted"] == 0

    def test_excepted_findings_do_not_fail_gate(self) -> None:
        rules = QualityRules(
            exceptions=(QualityException(rule_id="dq.stale_keyword.v1", component_type="dimensions", reason="frozen"),),
        )
        doc = _doc(dims=[_dim("evar1", "legacy_page")])
        failing = run_audits(
            doc, audit_naming_enabled=False, flag_stale_enabled=True, fail_on_quality=SeverityLevel.MEDIUM
        )
        assert failing["summary"]["verdict"] == "fail"
        passing = run_audits(
            doc,
            audit_naming_enabled=False,
            flag_stale_enabled=True,
            fail_on_quality=SeverityLevel.MEDIUM,
            rules=rules,
        )
        assert passing["summary"]["verdict"] == "pass"
        assert passing["issues"][0]["excepted"] is True

    def test_case_inconsistency_excepted_only_when_all_members_covered(self) -> None:
        doc = _doc(
            dims=[_dim("evar1", "page_name"), _dim("evar2", "site_name"), _dim("evar3", "pageType")],
            metrics=[_metric("event1", "orderCount")],
        )
        partial = QualityRules(
            exceptions=(
                QualityException(rule_id="dq.naming_case_inconsistency.v1", component_id="evar3", reason="vendor"),
            ),
        )
        block = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False, rules=partial)
        assert _issues(block, "dq.naming_case_inconsistency.v1")[0]["excepted"] is False

        full = QualityRules(
            exceptions=(
                QualityException(rule_id="dq.naming_case_inconsistency.v1", component_id="evar3", reason="vendor"),
                QualityException(rule_id="dq.naming_case_inconsistency.v1", component_type="metrics", reason="vendor"),
            ),
        )
        block = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False, rules=full)
        issue = _issues(block, "dq.naming_case_inconsistency.v1")[0]
        assert issue["excepted"] is True
        assert issue["exception_reason"] == "vendor"

    def test_naming_convention_exception(self) -> None:
        rules = QualityRules(
            naming={"dimensions": NamingRule(case="snake_case")},
            exceptions=(
                QualityException(rule_id="dq.naming_convention.v1", component_id="evar2", reason="legacy tag"),
            ),
        )
        doc = _doc(dims=[_dim("evar1", "page_name"), _dim("evar2", "PageName")])
        block = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False, rules=rules)
        (issue,) = _issues(block, "dq.naming_convention.v1")
        assert issue["excepted"] is True
        assert issue["exception_reason"] == "legacy tag"

    def test_summary_excepted_zero_without_rules(self) -> None:
        block = run_audits(self._doc(), audit_naming_enabled=False, flag_stale_enabled=True)
        assert block["summary"]["excepted"] == 0
        assert block["summary"]["total"] == 3


class TestCacheInvalidation:
    def test_policy_change_invalidates_cached_audit(self) -> None:
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        doc = _doc(dims=[_dim("evar1", "PageName")])
        r1 = QualityRules(naming={"dimensions": NamingRule(case="PascalCase")})
        r2 = QualityRules(naming={"dimensions": NamingRule(case="snake_case")})
        a = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False, rules=r1, cache=cache, rsid="rs1")
        b = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False, rules=r2, cache=cache, rsid="rs1")
        assert _issues(a, "dq.naming_convention.v1") == []
        assert len(_issues(b, "dq.naming_convention.v1")) == 1

    def test_exception_change_invalidates_cached_audit(self) -> None:
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        doc = _doc(dims=[_dim("evar1", "legacy_page")])
        exc = QualityRules(
            exceptions=(QualityException(rule_id="dq.stale_keyword.v1", component_id="evar1", reason="r"),),
        )
        a = run_audits(doc, audit_naming_enabled=False, flag_stale_enabled=True, cache=cache, rsid="rs1")
        b = run_audits(doc, audit_naming_enabled=False, flag_stale_enabled=True, rules=exc, cache=cache, rsid="rs1")
        assert a["issues"][0]["excepted"] is False
        assert b["issues"][0]["excepted"] is True

    def test_same_rules_hit_cache(self) -> None:
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        doc = _doc(dims=[_dim("evar1", "PageName")])
        rules = QualityRules(naming={"dimensions": NamingRule(case="snake_case")})
        a = run_audits(doc, audit_naming_enabled=True, flag_stale_enabled=False, rules=rules, cache=cache, rsid="rs1")
        b = run_audits(
            doc,
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=QualityRules(naming={"dimensions": NamingRule(case="snake_case")}),
            cache=cache,
            rsid="rs1",
        )
        assert a is b

    def test_vrs_rename_invalidates_when_vrs_rule_present(self) -> None:
        def vrs(name: str) -> models.VirtualReportSuite:
            return models.VirtualReportSuite(id="vrs_x", name=name, parent_rsid="rs1", timezone=None, description=None)

        cache = ValidationCache(max_size=10, ttl_seconds=60)
        rules = QualityRules(naming={"virtual_report_suites": NamingRule(case="kebab-case")})
        a = run_audits(
            _doc(vrs=[vrs("good-name")]),
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=rules,
            cache=cache,
            rsid="rs1",
        )
        b = run_audits(
            _doc(vrs=[vrs("Bad Name")]),
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=rules,
            cache=cache,
            rsid="rs1",
        )
        assert _issues(a, "dq.naming_convention.v1") == []
        assert len(_issues(b, "dq.naming_convention.v1")) == 1

    def test_standard_flag_change_invalidates(self) -> None:
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        rules = QualityRules(naming={"dimensions": NamingRule(case="snake_case")})
        a = run_audits(
            _doc(dims=[_dim("evar1", "Page", standardComponent=True)]),
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=rules,
            cache=cache,
            rsid="rs1",
        )
        b = run_audits(
            _doc(dims=[_dim("evar1", "Page")]),
            audit_naming_enabled=True,
            flag_stale_enabled=False,
            rules=rules,
            cache=cache,
            rsid="rs1",
        )
        assert _issues(a, "dq.naming_convention.v1") == []
        assert len(_issues(b, "dq.naming_convention.v1")) == 1

    def test_fingerprint_stable_and_distinct(self) -> None:
        a = QualityRules(naming={"metrics": NamingRule(case="any", pattern="x")})
        b = QualityRules(naming={"metrics": NamingRule(case="any", pattern="x")})
        c = QualityRules(naming={"metrics": NamingRule(case="any", pattern="y")})
        assert a.fingerprint() == b.fingerprint()
        assert a.fingerprint() != c.fingerprint()
