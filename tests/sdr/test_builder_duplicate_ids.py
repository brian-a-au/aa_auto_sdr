"""A capture never carries two components with the same id in one family.

Nothing deduped component rows, so a response with a repeated id produced a
document whose rows collapsed onto the last one during a diff, making the
unchanged count wrong. The classifications endpoint is
`/classifications/datasets/compatibilityMetrics/{rsid}`, which lists one row
per dataset-and-metric pair, so a dataset compatible with several metrics is
the realistic source.

Uniqueness is enforced here, at the one place every family passes through,
rather than on read: `--watch` reads back the snapshot it just wrote, and the
shared reader must stay able to open a file an older release produced.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.builder import build_sdr
from aa_auto_sdr.snapshot.schema import document_to_envelope

_CAPTURED_AT = datetime(2026, 10, 28, tzinfo=UTC)


class _FakeClient:
    """Returns the rows each fetcher is monkeypatched to hand back."""

    handle = object()
    retry_policy = None


def _patch_fetchers(monkeypatch: pytest.MonkeyPatch, **families) -> None:
    from aa_auto_sdr.sdr import builder

    monkeypatch.setattr(
        builder.fetch,
        "fetch_report_suite",
        lambda *_a, **_kw: models.ReportSuite(rsid="RS1", name="RS1", timezone=None, currency=None, parent_rsid=None),
    )
    for name, rows in families.items():
        if name in ("fetch_virtual_report_suites", "fetch_classification_datasets"):
            monkeypatch.setattr(builder.fetch, name, lambda *_a, _rows=rows, **_kw: models.FetchOutcome.healthy(_rows))
        else:
            monkeypatch.setattr(builder.fetch, name, lambda *_a, _rows=rows, **_kw: _rows)


def _defaults() -> dict:
    return {
        "fetch_dimensions": [],
        "fetch_metrics": [],
        "fetch_segments": [],
        "fetch_calculated_metrics": [],
        "fetch_virtual_report_suites": [],
        "fetch_classification_datasets": [],
    }


def _build(monkeypatch: pytest.MonkeyPatch, **overrides):
    _patch_fetchers(monkeypatch, **{**_defaults(), **overrides})
    return build_sdr(_FakeClient(), "RS1", captured_at=_CAPTURED_AT, tool_version="1.24.4")


def _classification(name: str, metric: str) -> models.ClassificationDataset:
    return models.ClassificationDataset(id="ds1", name=name, rsid="RS1", extra={"metric": metric})


def test_duplicate_classification_ids_are_collapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _build(
        monkeypatch,
        fetch_classification_datasets=[_classification("Campaign", "a"), _classification("Campaign", "b")],
    )
    assert [c.id for c in doc.classifications] == ["ds1"]
    # First row wins, so the kept row is the one the API listed first.
    assert doc.classifications[0].extra["metric"] == "a"


def test_duplicate_dimension_ids_are_collapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _dim(name: str) -> models.Dimension:
        return models.Dimension(
            id="variables/evar1",
            name=name,
            type="string",
            category=None,
            parent="",
            pathable=False,
            description=None,
            tags=[],
        )

    doc = _build(monkeypatch, fetch_dimensions=[_dim("First"), _dim("Second")])
    assert [d.name for d in doc.dimensions] == ["First"]


def test_distinct_ids_are_all_kept_and_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    def _metric(ident: str) -> models.Metric:
        return models.Metric(
            id=ident,
            name=ident,
            type="int",
            category=None,
            precision=0,
            segmentable=False,
            description=None,
            tags=[],
            data_group=None,
        )

    doc = _build(monkeypatch, fetch_metrics=[_metric("metrics/c"), _metric("metrics/a"), _metric("metrics/b")])
    assert [m.id for m in doc.metrics] == ["metrics/a", "metrics/b", "metrics/c"]


def test_the_envelope_a_capture_writes_reads_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression that matters: the tool must never write a snapshot it
    cannot open again."""
    from aa_auto_sdr.snapshot.schema import validate_envelope

    doc = _build(
        monkeypatch,
        fetch_classification_datasets=[_classification("Campaign", "a"), _classification("Campaign", "b")],
    )
    validate_envelope(document_to_envelope(doc))
