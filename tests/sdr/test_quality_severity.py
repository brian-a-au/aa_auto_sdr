"""SeverityLevel ladder + Issue dataclass + severity-promotion."""

from __future__ import annotations

import pytest

from aa_auto_sdr.sdr.quality import (
    _SEVERITY_RANK,
    _SEVERITY_TABLE_VERSION,
    Issue,
    SeverityLevel,
    _severity_for_case_inconsistency,
    _severity_for_stale_reason,
    has_quality_issues_at_or_above,
)


class TestSeverityLevel:
    def test_levels_in_descending_severity(self) -> None:
        order = list(SeverityLevel)
        assert order == [
            SeverityLevel.CRITICAL,
            SeverityLevel.HIGH,
            SeverityLevel.MEDIUM,
            SeverityLevel.LOW,
            SeverityLevel.INFO,
        ]

    def test_ranks_zero_to_four(self) -> None:
        assert _SEVERITY_RANK[SeverityLevel.CRITICAL] == 0
        assert _SEVERITY_RANK[SeverityLevel.INFO] == 4

    def test_string_value_uppercase(self) -> None:
        assert SeverityLevel.HIGH.value == "HIGH"

    def test_severity_table_version_format(self) -> None:
        # Bumped any time §3.4 mapping changes.
        assert _SEVERITY_TABLE_VERSION.startswith("v")


class TestHasIssuesAtOrAbove:
    def test_empty_list_returns_false(self) -> None:
        assert has_quality_issues_at_or_above([], SeverityLevel.HIGH) is False

    def test_match_at_threshold(self) -> None:
        issues = [Issue(SeverityLevel.HIGH, "naming", "stale_keyword", "evar5", "v_test", "x", {})]
        assert has_quality_issues_at_or_above(issues, SeverityLevel.HIGH) is True

    def test_match_above_threshold(self) -> None:
        issues = [Issue(SeverityLevel.CRITICAL, "naming", "empty_name", "evar5", "", "x", {})]
        assert has_quality_issues_at_or_above(issues, SeverityLevel.HIGH) is True

    def test_no_match_below_threshold(self) -> None:
        issues = [Issue(SeverityLevel.LOW, "naming", "version_suffix", "evar5", "v_v2", "x", {})]
        assert has_quality_issues_at_or_above(issues, SeverityLevel.HIGH) is False


class TestSeverityPromotion:
    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            ("stale_keyword:test", SeverityLevel.MEDIUM),
            ("stale_keyword:old", SeverityLevel.MEDIUM),
            ("stale_keyword:deprecated", SeverityLevel.MEDIUM),
            ("stale_keyword:legacy", SeverityLevel.MEDIUM),
            ("stale_keyword:obsolete", SeverityLevel.MEDIUM),
            ("stale_keyword:unused", SeverityLevel.MEDIUM),
            ("stale_keyword:temp", SeverityLevel.LOW),
            ("stale_keyword:backup", SeverityLevel.LOW),
            ("stale_keyword:copy", SeverityLevel.LOW),
            ("stale_keyword:archive", SeverityLevel.LOW),
            ("version_suffix:v2", SeverityLevel.LOW),
            ("date_pattern:20240101", SeverityLevel.LOW),
        ],
    )
    def test_stale_reason_severity(self, reason: str, expected: SeverityLevel) -> None:
        assert _severity_for_stale_reason(reason) == expected

    def test_unknown_reason_defaults_to_low(self) -> None:
        # Defensive default — never raise; unknown reasons get LOW.
        assert _severity_for_stale_reason("future_kind:something") == SeverityLevel.LOW

    def test_case_inconsistency_is_low(self) -> None:
        assert _severity_for_case_inconsistency() == SeverityLevel.LOW


class TestRunAuditsShape:
    """run_audits orchestrates audit_naming + detect_stale + severity-promotion."""

    def _bundle(self, *, with_stale: bool = True):
        # SdrDocument has the structural attrs run_audits expects via
        # _ComponentBundle Protocol. Use a real one.
        from datetime import UTC, datetime

        from aa_auto_sdr.api import models
        from aa_auto_sdr.sdr.document import SdrDocument

        rs = models.ReportSuite(rsid="rs1", name="RS1", timezone=None, currency=None, parent_rsid=None)
        dims = [
            models.Dimension(
                id="evar1",
                name="page_name",
                type="dimension",
                category=None,
                parent="",
                pathable=False,
                description=None,
            ),
        ]
        if with_stale:
            dims.append(
                models.Dimension(
                    id="evar2",
                    name="v_test_dim",
                    type="dimension",
                    category=None,
                    parent="",
                    pathable=False,
                    description=None,
                ),
            )
        return SdrDocument(
            report_suite=rs,
            dimensions=dims,
            metrics=[],
            segments=[],
            calculated_metrics=[],
            virtual_report_suites=[],
            classifications=[],
            captured_at=datetime.now(UTC),
            tool_version="1.12.0",
        )

    def test_returns_dict_with_v1_9_0_keys_plus_issues_and_summary(self) -> None:
        from aa_auto_sdr.sdr.quality import run_audits

        result = run_audits(self._bundle(), audit_naming_enabled=True, flag_stale_enabled=True)
        # v1.9.0 keys preserved
        assert "naming_audit" in result
        assert "stale_components" in result
        # v1.12.0 keys added
        assert "issues" in result
        assert "summary" in result
        # The stale dimension surfaces as one MEDIUM Issue.
        severities = [i["severity"] for i in result["issues"]]
        assert "MEDIUM" in severities
        # Summary tallies it.
        assert result["summary"]["by_severity"]["MEDIUM"] >= 1

    def test_summary_verdict_pass_when_no_threshold(self) -> None:
        from aa_auto_sdr.sdr.quality import run_audits

        result = run_audits(
            self._bundle(with_stale=False),
            audit_naming_enabled=True,
            flag_stale_enabled=True,
        )
        assert result["summary"]["verdict"] == "n/a"

    def test_summary_verdict_fail_when_threshold_breached(self) -> None:
        from aa_auto_sdr.sdr.quality import run_audits

        result = run_audits(
            self._bundle(),
            audit_naming_enabled=True,
            flag_stale_enabled=True,
            fail_on_quality=SeverityLevel.MEDIUM,
        )
        assert result["summary"]["verdict"] == "fail"
        assert result["summary"]["policy_threshold"] == "MEDIUM"

    def test_audits_disabled_returns_empty_quality(self) -> None:
        from aa_auto_sdr.sdr.quality import run_audits

        result = run_audits(
            self._bundle(),
            audit_naming_enabled=False,
            flag_stale_enabled=False,
        )
        assert result["issues"] == []
        assert result["summary"]["total"] == 0
