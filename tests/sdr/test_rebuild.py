"""sdr/rebuild.py: pure dict -> SdrDocument rebuild for --render-from.

Covers both input shapes (SDR JSON from `--format json`, snapshot envelopes
v1-v5), the provenance that must survive the rebuild (captured_at,
tool_version, scope, fetch status, quality), and boundary validation."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.core.exceptions import SdrPayloadError, SnapshotCorruptError, SnapshotSchemaError
from aa_auto_sdr.output.coverage import CoverageState, coverage_rows
from aa_auto_sdr.sdr import rebuild
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, FetchOutcomeMeta, RenderProvenance, SdrDocument
from aa_auto_sdr.snapshot.schema import document_to_envelope

V5_FIXTURE = Path(__file__).parent.parent / "fixtures" / "snapshot_v5_metrics_only.json"
RENDERED_AT = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)


def _doc(
    *,
    collected: tuple[str, ...] | None = COMPONENT_FAMILIES,
    fetch_status: dict[str, FetchOutcomeMeta] | None = None,
    quality: dict | None = None,
) -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid="demo.prod", name="Demo Production", timezone="US/Pacific", currency="USD", parent_rsid=None
        ),
        dimensions=[
            models.Dimension(
                id="variables/evar1",
                name="User ID",
                type="string",
                category="Conversion",
                parent="",
                pathable=False,
                description="Authenticated user",
                tags=["pii"],
                extra={"standardComponent": False},
            )
        ],
        metrics=[
            models.Metric(
                id="metrics/pageviews",
                name="Page Views",
                type="int",
                category="Traffic",
                precision=0,
                segmentable=True,
                description=None,
                data_group="Traffic",
            )
        ],
        segments=[
            models.Segment(
                id="s_1",
                name="Mobile",
                description=None,
                rsid="demo.prod",
                owner_id=42,
                definition={"func": "segment"},
                compatibility={"supported_products": ["oberon"]},
                created="2026-01-01",
            )
        ],
        calculated_metrics=[
            models.CalculatedMetric(
                id="cm_1",
                name="Conversion Rate",
                description="orders / visits",
                rsid="demo.prod",
                owner_id=None,
                polarity="positive",
                precision=2,
                type="percent",
                definition={"formula": {"func": "divide"}},
                categories=["KPI"],
            )
        ],
        virtual_report_suites=[
            models.VirtualReportSuite(
                id="vrs_1",
                name="VRS One",
                parent_rsid="demo.prod",
                timezone=None,
                description=None,
                segment_list=["s_1"],
                curated_components=[{"id": "metrics/pageviews"}],
            )
        ],
        classifications=[models.ClassificationDataset(id="ds_1", name="Campaigns", rsid="demo.prod")],
        captured_at=datetime(2026, 4, 25, 17, 30, tzinfo=UTC),
        tool_version="1.21.0",
        fetch_status=fetch_status or {},
        quality=quality,
        collected_components=collected,
    )


def _sdr_json(doc: SdrDocument) -> dict:
    # Through a JSON round trip, exactly as the file on disk would be read.
    return json.loads(json.dumps(doc.to_dict()))


def _envelope(doc: SdrDocument) -> dict:
    return json.loads(json.dumps(document_to_envelope(doc)))


# --- shape detection ---------------------------------------------------------


def test_payload_kind_detects_both_shapes() -> None:
    doc = _doc()
    assert rebuild.payload_kind(_sdr_json(doc)) == "sdr_json"
    assert rebuild.payload_kind(_envelope(doc)) == "envelope"


@pytest.mark.parametrize("payload", [[], [{"report_suite": {}}], "x", 3, None, {"nothing": "here"}])
def test_payload_kind_rejects_unknown_shape(payload) -> None:
    with pytest.raises(SdrPayloadError, match="unrecognized"):
        rebuild.payload_kind(payload)


# --- SDR JSON round trip -----------------------------------------------------


def test_sdr_json_round_trip_is_lossless() -> None:
    doc = _doc(
        fetch_status={"virtual_report_suites": FetchOutcomeMeta(status="partial", expansion_level="minimal")},
        quality={"summary": {"verdict": "pass", "total": 0, "by_severity": {}}, "issues": []},
    )
    rebuilt = rebuild.document_from_payload(_sdr_json(doc), rendered_at=RENDERED_AT, rendering_tool_version="9.9.9")
    assert rebuilt.captured_at == doc.captured_at
    assert rebuilt.tool_version == "1.21.0"
    assert rebuilt.rendered == RenderProvenance(rendered_at=RENDERED_AT, tool_version="9.9.9")
    expected = doc.to_dict()
    actual = rebuilt.to_dict()
    assert actual.pop("rendered_at") == RENDERED_AT.isoformat()
    assert actual.pop("rendered_by_tool_version") == "9.9.9"
    assert actual == expected


def test_sdr_json_filtered_scope_survives() -> None:
    doc = _doc(collected=("metrics",))
    rebuilt = rebuild.document_from_payload(_sdr_json(doc), rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert rebuilt.collected_components == ("metrics",)


def test_sdr_json_without_scope_key_stays_unknown() -> None:
    payload = _sdr_json(_doc())
    del payload["collected_components"]
    del payload["fetch_status"]
    del payload["quality"]
    rebuilt = rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert rebuilt.collected_components is None
    assert rebuilt.fetch_status == {}
    assert rebuilt.quality is None


def test_rerendering_rendered_json_replaces_provenance() -> None:
    first = rebuild.document_from_payload(_sdr_json(_doc()), rendered_at=RENDERED_AT, rendering_tool_version="1.0")
    later = datetime(2026, 11, 1, tzinfo=UTC)
    again = rebuild.document_from_payload(
        json.loads(json.dumps(first.to_dict())), rendered_at=later, rendering_tool_version="2.0"
    )
    assert again.captured_at == first.captured_at
    assert again.rendered == RenderProvenance(rendered_at=later, tool_version="2.0")


def test_rendered_provenance_absent_from_normal_to_dict() -> None:
    payload = _doc().to_dict()
    assert "rendered_at" not in payload
    assert "rendered_by_tool_version" not in payload


# --- envelopes ---------------------------------------------------------------


def test_v4_envelope_rebuild_matches_document() -> None:
    doc = _doc(
        fetch_status={
            "classifications": FetchOutcomeMeta(status="degraded", expansion_level=None),
            "virtual_report_suites": FetchOutcomeMeta(status="partial", expansion_level="minimal"),
        },
        quality={"summary": {"verdict": "fail", "total": 1, "by_severity": {"HIGH": 1}}, "issues": []},
    )
    env = _envelope(doc)
    assert env["schema"] == "aa-sdr-snapshot/v4"
    rebuilt = rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert rebuilt.fetch_status == doc.fetch_status
    assert rebuilt.collected_components == COMPONENT_FAMILIES
    assert rebuilt.quality == doc.quality
    actual = rebuilt.to_dict()
    actual.pop("rendered_at")
    actual.pop("rendered_by_tool_version")
    assert actual == doc.to_dict()


def test_v5_envelope_keeps_filtered_scope() -> None:
    env = json.loads(V5_FIXTURE.read_text())
    rebuilt = rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert rebuilt.collected_components == ("metrics",)
    states = {row.family: row.state for row in coverage_rows(rebuilt)}
    assert states["dimensions"] is CoverageState.EXCLUDED
    assert states["metrics"] in (CoverageState.COLLECTED, CoverageState.COLLECTED_EMPTY)


def test_v1_envelope_keeps_unknown_scope_never_collected_empty() -> None:
    env = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "rs1",
        "captured_at": "2026-04-26T17:29:01+00:00",
        "tool_version": "1.0.0",
        "components": {
            "report_suite": {"rsid": "rs1", "name": "RS One", "timezone": None, "currency": None, "parent_rsid": None},
            "dimensions": [],
            "metrics": [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }
    rebuilt = rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert rebuilt.collected_components is None
    assert rebuilt.fetch_status == {}
    assert rebuilt.quality is None
    assert rebuilt.tool_version == "1.0.0"
    assert rebuilt.captured_at == datetime(2026, 4, 26, 17, 29, 1, tzinfo=UTC)
    for row in coverage_rows(rebuilt):
        assert row.state is CoverageState.UNKNOWN_SCOPE
        assert row.state is not CoverageState.COLLECTED_EMPTY


def test_envelope_missing_sections_and_report_suite_default() -> None:
    env = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "rs1",
        "captured_at": "2026-04-26T17:29:01+00:00",
        "tool_version": "1.0.0",
        "components": {},
    }
    rebuilt = rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert rebuilt.report_suite.rsid == "rs1"
    assert rebuilt.report_suite.name == "rs1"
    assert rebuilt.dimensions == []


def test_envelope_unsupported_schema_raises_schema_error() -> None:
    env = _envelope(_doc())
    env["schema"] = "aa-sdr-snapshot/v99"
    with pytest.raises(SnapshotSchemaError):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_envelope_unknown_degraded_family_raises() -> None:
    env = _envelope(_doc(collected=None))
    env["degraded_components"] = ["widgets"]
    with pytest.raises(SnapshotCorruptError, match="widgets"):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_envelope_bad_partial_level_raises() -> None:
    env = _envelope(_doc(collected=None))
    env["partial_components"] = {"virtual_report_suites": 3}
    with pytest.raises(SnapshotCorruptError, match="expansion level"):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


# --- row validation (both shapes) --------------------------------------------


def _sdr_and_env_cases():
    doc = _doc()
    return [
        (_sdr_json(doc), SdrPayloadError, lambda p: p),
        (_envelope(doc), SnapshotCorruptError, lambda p: p["components"]),
    ]


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_duplicate_ids_rejected(payload, error, section) -> None:
    rows = section(payload)["metrics"]
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(error, match=r"duplicate.*metrics.*metrics/pageviews"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_missing_id_rejected(payload, error, section) -> None:
    del section(payload)["dimensions"][0]["id"]
    with pytest.raises(error, match=r"dimensions\[0\].*'id'"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_empty_id_rejected(payload, error, section) -> None:
    section(payload)["segments"][0]["id"] = ""
    with pytest.raises(error, match=r"segments\[0\].*'id'"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_wrong_type_for_required_field_rejected(payload, error, section) -> None:
    section(payload)["metrics"][0]["precision"] = "two"
    with pytest.raises(error, match=r"metrics\[0\].*'precision'.*int"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_bool_is_not_an_int(payload, error, section) -> None:
    section(payload)["metrics"][0]["precision"] = True
    with pytest.raises(error, match="'precision'"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_missing_required_field_rejected(payload, error, section) -> None:
    del section(payload)["calculated_metrics"][0]["polarity"]
    with pytest.raises(error, match=r"calculated_metrics\[0\].*missing.*'polarity'"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(("payload", "error", "section"), _sdr_and_env_cases(), ids=["sdr_json", "envelope"])
def test_missing_optional_fields_default(payload, error, section) -> None:
    row = section(payload)["dimensions"][0]
    del row["description"]
    del row["tags"]
    del row["extra"]
    rebuilt = rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")
    dim = rebuilt.dimensions[0]
    assert dim.description is None
    assert dim.tags == []
    assert dim.extra == {}


def test_non_dict_row_rejected_in_sdr_json() -> None:
    payload = _sdr_json(_doc())
    payload["classifications"] = ["ds_1"]
    with pytest.raises(SdrPayloadError, match=r"classifications\[0\].*object"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_non_dict_row_rejected_in_envelope() -> None:
    env = _envelope(_doc())
    env["components"]["classifications"] = ["ds_1"]
    with pytest.raises(SnapshotCorruptError):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_section_not_a_list_rejected() -> None:
    payload = _sdr_json(_doc())
    payload["metrics"] = {"id": "x"}
    with pytest.raises(SdrPayloadError, match="'metrics' must be a list"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda p: p.pop("captured_at"), "captured_at"),
        (lambda p: p.__setitem__("captured_at", "yesterday"), "captured_at"),
        (lambda p: p.__setitem__("captured_at", "2026-04-25T17:30:00"), "timezone"),
        (lambda p: p.pop("tool_version"), "tool_version"),
        (lambda p: p.__setitem__("report_suite", "demo.prod"), "report_suite"),
        (lambda p: p["report_suite"].pop("rsid"), "rsid"),
        (lambda p: p.__setitem__("quality", ["x"]), "quality"),
        (lambda p: p.__setitem__("collected_components", ["widgets"]), "widgets"),
        (lambda p: p.__setitem__("collected_components", ["metrics", "metrics"]), "duplicate"),
        (lambda p: p.__setitem__("collected_components", "metrics"), "collected_components"),
        (lambda p: p.__setitem__("fetch_status", {"widgets": {"status": "degraded"}}), "widgets"),
        (lambda p: p.__setitem__("fetch_status", {"metrics": {"status": "broken"}}), "status"),
        (lambda p: p.__setitem__("fetch_status", {"metrics": "degraded"}), "fetch_status"),
        (lambda p: p.__setitem__("fetch_status", []), "fetch_status"),
    ],
)
def test_sdr_json_header_validation(mutate, match) -> None:
    payload = _sdr_json(_doc())
    mutate(payload)
    with pytest.raises(SdrPayloadError, match=match):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_sdr_json_fetch_status_outside_scope_rejected() -> None:
    payload = _sdr_json(_doc(collected=("metrics",)))
    payload["fetch_status"] = {"classifications": {"status": "degraded", "expansion_level": None}}
    with pytest.raises(SdrPayloadError, match="classifications"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda e: e.__setitem__("rsid", ""), "rsid"),
        (lambda e: e.__setitem__("tool_version", 7), "tool_version"),
        (lambda e: e.__setitem__("partial_components", {"widgets": "minimal"}), "widgets"),
        (lambda e: e["components"]["metrics"][0].__setitem__("tags", "x"), "tags"),
    ],
)
def test_envelope_header_validation(mutate, match) -> None:
    env = _envelope(_doc(collected=None))
    mutate(env)
    with pytest.raises(SnapshotCorruptError, match=match):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_sdr_json_bad_expansion_level_rejected() -> None:
    payload = _sdr_json(_doc())
    payload["fetch_status"] = {"metrics": {"status": "partial", "expansion_level": 1}}
    with pytest.raises(SdrPayloadError, match="expansion_level"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


# --- rsid must be a plain file-name-safe token (it names output files) -------

_UNSAFE_RSIDS = ["../escaped", "/abs/path", "a/b", "..\\escaped", "a\\b", "rs\x00x", ".hidden", "..", "."]


@pytest.mark.parametrize("bad", _UNSAFE_RSIDS)
def test_sdr_json_unsafe_rsid_rejected(bad: str) -> None:
    payload = _sdr_json(_doc())
    payload["report_suite"]["rsid"] = bad
    with pytest.raises(SdrPayloadError, match=r"report_suite\.rsid"):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize("bad", _UNSAFE_RSIDS)
def test_envelope_unsafe_rsid_rejected(bad: str) -> None:
    env = _envelope(_doc())
    env["rsid"] = bad
    env["components"]["report_suite"]["rsid"] = bad
    with pytest.raises(SnapshotCorruptError, match="rsid"):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize("bad", _UNSAFE_RSIDS)
def test_envelope_without_report_suite_unsafe_rsid_rejected(bad: str) -> None:
    env = _envelope(_doc())
    env["rsid"] = bad
    del env["components"]["report_suite"]
    with pytest.raises(SnapshotCorruptError, match="rsid"):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_envelope_rsid_mismatch_rejected() -> None:
    env = _envelope(_doc())
    env["components"]["report_suite"]["rsid"] = "other.rs"
    with pytest.raises(SnapshotCorruptError, match=r"'demo\.prod'.*'other\.rs'"):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


@pytest.mark.parametrize("ok", ["demo.prod", "examplersid1", "acme-prod_2", "RS1"])
def test_ordinary_rsids_accepted(ok: str) -> None:
    payload = _sdr_json(_doc())
    payload["report_suite"]["rsid"] = ok
    doc = rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert doc.report_suite.rsid == ok


@pytest.mark.parametrize(
    ("quality", "match"),
    [
        ({"summary": "oops"}, r"SDR JSON 'quality.summary' must be an object"),
        ({"summary": {"by_severity": []}}, r"SDR JSON 'quality.summary.by_severity' must be an object"),
        ({"issues": "x"}, r"SDR JSON 'quality.issues' must be a list of objects"),
        ({"issues": ["x"]}, r"SDR JSON 'quality.issues' must be a list of objects"),
        ({"stale_components": {}}, r"SDR JSON 'quality.stale_components' must be a list of objects"),
        ({"naming_audit": []}, r"SDR JSON 'quality.naming_audit' must be an object"),
    ],
)
def test_sdr_json_malformed_quality_block_rejected(quality: dict, match: str) -> None:
    # The writers read these parts; a wrong shape used to pass rebuild and
    # crash later with AttributeError. Same rules as snapshot validate_envelope.
    payload = _sdr_json(_doc())
    payload["quality"] = quality
    with pytest.raises(SdrPayloadError, match=match):
        rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_envelope_malformed_quality_block_already_rejected() -> None:
    env = _envelope(_doc())
    env["quality"] = {"summary": "oops"}
    with pytest.raises(SnapshotCorruptError, match=r"quality.summary must be a dict"):
        rebuild.document_from_payload(env, rendered_at=RENDERED_AT, rendering_tool_version="x")


def test_sdr_json_quality_block_without_parts_accepted() -> None:
    payload = _sdr_json(_doc())
    payload["quality"] = {}
    doc = rebuild.document_from_payload(payload, rendered_at=RENDERED_AT, rendering_tool_version="x")
    assert doc.quality == {}
