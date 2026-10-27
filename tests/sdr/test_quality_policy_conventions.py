"""Policy-file schema for naming rules and reasoned exceptions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.sdr.quality import NamingRule, QualityException, QualityRules, SeverityLevel
from aa_auto_sdr.sdr.quality_policy import load_policy


def _load(tmp_path: Path, payload: Any):
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(payload))
    return load_policy(p)


def _exc(**kw: Any) -> dict[str, Any]:
    base = {"rule_id": "dq.stale_keyword.v1", "component_id": "evar1", "reason": "kept"}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not None}


class TestSeverityCaseInsensitive:
    @pytest.mark.parametrize("raw", ["high", "High", " HIGH "])
    def test_accepted(self, tmp_path: Path, raw: str) -> None:
        assert _load(tmp_path, {"fail_on_quality": raw}).fail_on_quality is SeverityLevel.HIGH

    def test_bad_value_still_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="fail_on_quality"):
            _load(tmp_path, {"fail_on_quality": "extreme"})


class TestNamingSchema:
    def test_valid_naming(self, tmp_path: Path) -> None:
        policy = _load(
            tmp_path,
            {
                "naming": {
                    "dimensions": {"case": "snake_case"},
                    "metrics": {"pattern": "kpi_.*"},
                    "calculated-metrics": {"case": "Title Case", "pattern": "CM .*"},
                },
            },
        )
        assert policy.naming == {
            "dimensions": NamingRule(case="snake_case"),
            "metrics": NamingRule(pattern="kpi_.*"),
            "calculated_metrics": NamingRule(case="Title Case", pattern="CM .*"),
        }
        assert policy.rules == QualityRules(naming=policy.naming)

    @pytest.mark.parametrize("style", ["snake_case", "camelCase", "PascalCase", "Title Case", "kebab-case", "any"])
    def test_every_case_style_accepted(self, tmp_path: Path, style: str) -> None:
        assert _load(tmp_path, {"naming": {"segments": {"case": style}}}).naming["segments"].case == style

    @pytest.mark.parametrize(
        ("naming", "match"),
        [
            ([], "naming must be an object"),
            ({"widgets": {"case": "any"}}, "unknown component type"),
            ({"dimensions": "snake_case"}, "must be an object"),
            ({"dimensions": {}}, "case and/or pattern"),
            ({"dimensions": {"case": "SCREAMING"}}, "case style"),
            ({"dimensions": {"case": 3}}, "case style"),
            ({"dimensions": {"pattern": "("}}, "invalid regex"),
            ({"dimensions": {"pattern": ""}}, "pattern"),
            ({"dimensions": {"case": "any", "prefix": "x"}}, "unknown key"),
        ],
    )
    def test_bad_naming_rejected(self, tmp_path: Path, naming: Any, match: str) -> None:
        with pytest.raises(ConfigError, match=match):
            _load(tmp_path, {"naming": naming})


class TestExceptionsSchema:
    def test_valid_exceptions(self, tmp_path: Path) -> None:
        policy = _load(
            tmp_path,
            {
                "exceptions": [
                    _exc(),
                    {"rule_id": "dq.naming_convention.v1", "component-type": "metrics", "reason": "vendor names"},
                ],
            },
        )
        assert policy.exceptions == (
            QualityException(rule_id="dq.stale_keyword.v1", component_id="evar1", reason="kept"),
            QualityException(rule_id="dq.naming_convention.v1", component_type="metrics", reason="vendor names"),
        )
        assert policy.rules is not None
        assert policy.rules.exceptions == policy.exceptions

    def test_empty_policy_has_no_rules(self, tmp_path: Path) -> None:
        assert _load(tmp_path, {"fail_on_quality": "HIGH"}).rules is None

    @pytest.mark.parametrize(
        ("exceptions", "match"),
        [
            ({}, "exceptions must be a list"),
            (["x"], "must be an object"),
            ([_exc(reason=None)], "reason"),
            ([_exc(reason="   ")], "reason"),
            ([_exc(reason=5)], "reason"),
            ([_exc(rule_id=None)], "rule_id"),
            ([_exc(rule_id="dq.nope.v1")], "unknown rule_id"),
            ([_exc(rule_id="*")], "wildcard"),
            ([_exc(rule_id="dq.custom.unknown")], "unknown rule_id"),
            ([_exc(component_id=None)], "exactly one of"),
            ([_exc(component_type="dimensions")], "exactly one of"),
            ([_exc(component_id="")], "component_id"),
            ([_exc(component_id=None, component_type="widgets")], "component_type"),
            ([_exc(extra="x")], "unknown key"),
            ([_exc(), _exc(reason="different")], "duplicate exception"),
        ],
    )
    def test_bad_exceptions_rejected(self, tmp_path: Path, exceptions: Any, match: str) -> None:
        with pytest.raises(ConfigError, match=match):
            _load(tmp_path, {"exceptions": exceptions})

    def test_dropped_keys_still_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="max_issues"):
            _load(tmp_path, {"max_issues": 3, "naming": {"dimensions": {"case": "any"}}})

    def test_nested_envelope_carries_rules(self, tmp_path: Path) -> None:
        policy = _load(tmp_path, {"quality_policy": {"exceptions": [_exc()]}})
        assert len(policy.exceptions) == 1
