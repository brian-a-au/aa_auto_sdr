"""Top-level `coverage` object in SDR JSON (cja_auto_sdr-aligned shape).

`coverage = {families: [{family, state, count, detail}], quality: {state,
detail, issue_count, severity_counts, gate}}`. It is derived output: SDR JSON
carries it, snapshot envelopes never do."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.api import models as m
from aa_auto_sdr.output.coverage import coverage_json
from aa_auto_sdr.output.writers.json import JsonWriter
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, FetchOutcomeMeta, SdrDocument
from aa_auto_sdr.sdr.rebuild import document_from_payload
from aa_auto_sdr.snapshot import schema

_DIMENSION = m.Dimension(
    id="variables/evar1",
    name="User ID",
    type="string",
    category="Conversion",
    parent="",
    pathable=False,
    description=None,
)
_METRIC = m.Metric(
    id="metrics/pageviews",
    name="Page Views",
    type="int",
    category=None,
    precision=0,
    segmentable=True,
    description=None,
)
_CLASSIFICATION = m.ClassificationDataset(id="ds_1", name="Campaign", rsid="demo.prod")

_FAMILY_ORDER = [
    "dimensions",
    "metrics",
    "segments",
    "calculated_metrics",
    "virtual_report_suites",
    "classifications",
]


def _quality(*, verdict: str, threshold: str | None) -> dict:
    summary: dict = {
        "by_severity": {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 1, "INFO": 0},
        "total": 2,
        "verdict": verdict,
    }
    if threshold is not None:
        summary["policy_threshold"] = threshold
    return {
        "naming_audit": {},
        "stale_components": [],
        "issues": [
            {"severity": "HIGH", "category": "stale", "type": "dimension", "item_id": "a", "item_name": "a"},
            {"severity": "LOW", "category": "naming", "type": "dimensions", "item_id": "b", "item_name": ""},
        ],
        "summary": summary,
    }


def _doc(**overrides) -> SdrDocument:
    base = SdrDocument(
        report_suite=m.ReportSuite(rsid="demo.prod", name="Demo", timezone=None, currency=None, parent_rsid=None),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="9.9.9",
        collected_components=COMPONENT_FAMILIES,
    )
    return replace(base, **overrides)


def _mixed_doc() -> SdrDocument:
    return _doc(
        dimensions=[_DIMENSION],
        classifications=[_CLASSIFICATION],
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None),
            "classifications": FetchOutcomeMeta(status="partial", expansion_level="rsid_only"),
        },
    )


def _families(payload: dict) -> dict[str, dict]:
    return {f["family"]: f for f in payload["coverage"]["families"]}


def test_to_dict_has_coverage_with_cja_shape() -> None:
    payload = _doc(dimensions=[_DIMENSION]).to_dict()
    cov = payload["coverage"]
    assert set(cov) == {"families", "quality"}
    assert [f["family"] for f in cov["families"]] == _FAMILY_ORDER
    for fam in cov["families"]:
        assert set(fam) == {"family", "state", "count", "detail"}
    assert set(cov["quality"]) == {"state", "detail", "issue_count", "severity_counts", "gate"}


def test_healthy_collected_and_collected_empty() -> None:
    fams = _families(_doc(dimensions=[_DIMENSION]).to_dict())
    assert fams["dimensions"] == {"family": "dimensions", "state": "collected", "count": 1, "detail": "Collected"}
    assert fams["metrics"]["state"] == "collected_empty"
    assert fams["metrics"]["count"] == 0
    assert fams["metrics"]["detail"] == "Collected — no components"


def test_excluded_families() -> None:
    fams = _families(_doc(metrics=[_METRIC], collected_components=("metrics",)).to_dict())
    assert fams["metrics"]["state"] == "collected"
    for family in set(_FAMILY_ORDER) - {"metrics"}:
        assert fams[family]["state"] == "excluded"
        assert fams[family]["detail"] == "Not collected in this capture"


def test_degraded_and_partial_detail_carries_expansion_level() -> None:
    fams = _families(_mixed_doc().to_dict())
    assert fams["virtual_report_suites"] == {
        "family": "virtual_report_suites",
        "state": "degraded",
        "count": 0,
        "detail": "Fetch degraded — no data",
    }
    assert fams["classifications"] == {
        "family": "classifications",
        "state": "partial",
        "count": 1,
        "detail": "Partial fetch (expansion level: rsid_only)",
    }


def test_unknown_scope() -> None:
    fams = _families(_doc(collected_components=None).to_dict())
    assert {f["state"] for f in fams.values()} == {"unknown_scope"}


def test_quality_not_run() -> None:
    quality = _doc().to_dict()["coverage"]["quality"]
    assert quality == {
        "state": "not_run",
        "detail": "No quality audit ran.",
        "issue_count": None,
        "severity_counts": {},
        "gate": None,
    }


def test_quality_ran_with_gate() -> None:
    quality = _doc(quality=_quality(verdict="fail", threshold="HIGH")).to_dict()["coverage"]["quality"]
    assert quality["state"] == "ran"
    assert quality["issue_count"] == 2
    assert quality["severity_counts"] == {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 1, "INFO": 0}
    assert quality["gate"] == {"threshold": "HIGH", "verdict": "fail"}
    assert quality["detail"].startswith("Quality gate FAIL at threshold HIGH")


def test_quality_ran_without_gate_policy() -> None:
    quality = _doc(quality=_quality(verdict="n/a", threshold=None)).to_dict()["coverage"]["quality"]
    assert quality["state"] == "ran"
    # No --fail-on-quality threshold: no gate, as in cja_auto_sdr.
    assert quality["gate"] is None
    assert quality["detail"].startswith("Quality audit ran with no gate policy")


def test_coverage_json_helper_matches_to_dict() -> None:
    doc = _mixed_doc()
    assert coverage_json(doc) == doc.to_dict()["coverage"]


def test_json_writer_file_carries_coverage(tmp_path: Path) -> None:
    [path] = JsonWriter().write(_mixed_doc(), tmp_path / "demo.prod.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert _families(data)["classifications"]["state"] == "partial"
    assert data["coverage"]["quality"]["state"] == "not_run"


def test_render_from_ignores_coverage_key() -> None:
    payload = _mixed_doc().to_dict()
    payload["coverage"] = {"families": "garbage"}
    rebuilt = document_from_payload(
        json.loads(json.dumps(payload)),
        rendered_at=datetime(2026, 5, 1, tzinfo=UTC),
        rendering_tool_version="9.9.9",
    )
    assert rebuilt.to_dict()["coverage"] == coverage_json(_mixed_doc())


# --- snapshots never carry coverage ----------------------------------------

# sha256 of json.dumps(envelope, sort_keys=True) for these docs, recorded
# before SDR JSON gained `coverage`. A change here means the snapshot envelope
# changed, which this feature must not do.
_ENVELOPE_SHA256 = {
    "mixed": "6214464348216bc5e1cb2b22097b4e30633e1d028dc3400b1f39835aa94aaa99",
    "audited_filtered": "f1d9bf8a43f6bfeccfb3d2d69a71601e8078e34c97196e6ef5145f7b4d7f1fa6",
}


def _envelope_docs() -> dict[str, SdrDocument]:
    return {
        "mixed": _mixed_doc(),
        "audited_filtered": _doc(
            metrics=[_METRIC],
            collected_components=("metrics",),
            quality=_quality(verdict="fail", threshold="HIGH"),
        ),
    }


@pytest.mark.parametrize("name", sorted(_ENVELOPE_SHA256))
@pytest.mark.parametrize("reuse_payload", [False, True])
def test_snapshot_envelope_is_byte_identical(name: str, reuse_payload: bool) -> None:
    doc = _envelope_docs()[name]
    env = schema.document_to_envelope(doc, payload=doc.to_dict() if reuse_payload else None)
    assert "coverage" not in env
    assert "coverage" not in env["components"]
    digest = hashlib.sha256(json.dumps(env, sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == _ENVELOPE_SHA256[name]
