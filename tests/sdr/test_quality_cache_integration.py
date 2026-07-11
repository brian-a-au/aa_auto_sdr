"""Cache integration in quality.run_audits — first ValidationCache caller."""

from __future__ import annotations

from datetime import UTC, datetime

from aa_auto_sdr.api import models
from aa_auto_sdr.api.cache import ValidationCache
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.sdr.quality import (
    _SEVERITY_TABLE_VERSION,
    _cache_key,
    run_audits,
)


def _dim(idx: int, *, stale: bool = True) -> models.Dimension:
    return models.Dimension(
        id=f"evar{idx}",
        name=f"v_test_dim{idx}" if stale else f"page_name{idx}",
        type="dimension",
        category=None,
        parent="",
        pathable=False,
        description=None,
    )


def _bundle(stale_count: int = 1) -> SdrDocument:
    rs = models.ReportSuite(rsid="rs1", name="RS1", timezone=None, currency=None, parent_rsid=None)
    dims = [_dim(i + 1) for i in range(stale_count)]
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


class TestCacheKey:
    def test_stable_for_same_inputs(self) -> None:
        items = [_dim(1)]
        k1 = _cache_key("rs1", "dimensions", items, _SEVERITY_TABLE_VERSION)
        k2 = _cache_key("rs1", "dimensions", items, _SEVERITY_TABLE_VERSION)
        assert k1 == k2

    def test_changes_with_severity_table_version(self) -> None:
        items = [_dim(1)]
        k1 = _cache_key("rs1", "dimensions", items, "v1.12.0")
        k2 = _cache_key("rs1", "dimensions", items, "v1.13.0")
        assert k1 != k2

    def test_changes_with_rsid(self) -> None:
        items = [_dim(1)]
        k1 = _cache_key("rs1", "dimensions", items, _SEVERITY_TABLE_VERSION)
        k2 = _cache_key("rs2", "dimensions", items, _SEVERITY_TABLE_VERSION)
        assert k1 != k2

    def test_changes_with_component_type(self) -> None:
        items = [_dim(1)]
        k1 = _cache_key("rs1", "dimensions", items, _SEVERITY_TABLE_VERSION)
        k2 = _cache_key("rs1", "metrics", items, _SEVERITY_TABLE_VERSION)
        assert k1 != k2


class TestRunAuditsCache:
    def test_no_cache_passes_through_unchanged(self) -> None:
        result = run_audits(_bundle(), audit_naming_enabled=True, flag_stale_enabled=True, cache=None)
        assert result["summary"]["total"] >= 1

    def test_cache_hit_skips_recompute(self) -> None:
        cache = ValidationCache(max_size=100, ttl_seconds=3600)
        b = _bundle()
        # Prime cache.
        run_audits(b, audit_naming_enabled=True, flag_stale_enabled=True, cache=cache, rsid="rs1")
        stats_after_first = cache.stats()
        # Re-run; expect a cache hit.
        run_audits(b, audit_naming_enabled=True, flag_stale_enabled=True, cache=cache, rsid="rs1")
        stats_after_second = cache.stats()
        assert stats_after_second["hits"] > stats_after_first["hits"]

    def test_cache_without_rsid_disabled_defensively(self) -> None:
        """A cache is provided but no rsid: disabled to prevent cross-RSID leakage."""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)
        run_audits(_bundle(), audit_naming_enabled=True, flag_stale_enabled=True, cache=cache, rsid="")
        # Cache should be untouched.
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestCacheKeyNameSensitivity:
    def test_rename_changes_key(self) -> None:
        """The audits are name-based (stale keywords, case styles) — a renamed
        component with the same id must not reuse a stale cached block."""
        before = [_dim(1, stale=True)]
        after = [_dim(1, stale=False)]  # same id, different name
        k1 = _cache_key("rs1", "dimensions", before, _SEVERITY_TABLE_VERSION)
        k2 = _cache_key("rs1", "dimensions", after, _SEVERITY_TABLE_VERSION)
        assert k1 != k2

    def test_rename_invalidates_run_audits_result(self) -> None:
        cache = ValidationCache(max_size=100, ttl_seconds=3600)
        stale = run_audits(_bundle(), audit_naming_enabled=True, flag_stale_enabled=True, cache=cache, rsid="rs1")
        assert stale["summary"]["total"] >= 1
        renamed = _bundle()
        renamed = type(renamed)(
            report_suite=renamed.report_suite,
            dimensions=[_dim(1, stale=False)],
            metrics=[],
            segments=[],
            calculated_metrics=[],
            virtual_report_suites=[],
            classifications=[],
            captured_at=renamed.captured_at,
            tool_version=renamed.tool_version,
        )
        clean = run_audits(renamed, audit_naming_enabled=True, flag_stale_enabled=True, cache=cache, rsid="rs1")
        assert clean["summary"]["total"] == 0
