"""Capture scope in snapshot envelopes: v4 for full captures, v5 for filtered ones.

Every new envelope carries a top-level `collected_components` list. A full
capture keeps `aa-sdr-snapshot/v4` so released readers still load it; a
filtered capture writes `aa-sdr-snapshot/v5` so released readers refuse it
instead of reading the excluded families as deletions.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.core.exceptions import SnapshotCorruptError, SnapshotSchemaError
from aa_auto_sdr.core.json_io import write_json
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, FetchOutcomeMeta, SdrDocument
from aa_auto_sdr.snapshot.schema import document_to_envelope, validate_envelope
from aa_auto_sdr.snapshot.store import load_snapshot, save_snapshot

V5_FIXTURE = Path(__file__).parent.parent / "fixtures" / "snapshot_v5_metrics_only.json"


def _doc(
    *,
    collected: tuple[str, ...] | None = COMPONENT_FAMILIES,
    fetch_status: dict[str, FetchOutcomeMeta] | None = None,
) -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(
            rsid="demo.prod",
            name="Demo Production",
            timezone="US/Pacific",
            currency="USD",
            parent_rsid=None,
        ),
        dimensions=[],
        metrics=[
            models.Metric(
                id="metrics/pageviews",
                name="Page Views",
                type="int",
                category="Traffic",
                precision=0,
                segmentable=True,
                description="Total page views",
            ),
        ],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 10, 27, 12, 0, tzinfo=UTC),
        tool_version="1.22.0",
        fetch_status=fetch_status or {},
        collected_components=collected,
    )


def _v5_env() -> dict:
    return json.loads(V5_FIXTURE.read_text())


# --- writing -------------------------------------------------------------


def test_component_families_are_the_six_sorted_names() -> None:
    assert COMPONENT_FAMILIES == (
        "calculated_metrics",
        "classifications",
        "dimensions",
        "metrics",
        "segments",
        "virtual_report_suites",
    )


def test_full_capture_writes_v4_with_collected_components() -> None:
    env = document_to_envelope(_doc())
    assert env["schema"] == "aa-sdr-snapshot/v4"
    assert env["collected_components"] == list(COMPONENT_FAMILIES)


def test_filtered_capture_writes_v5() -> None:
    env = document_to_envelope(_doc(collected=("metrics",)))
    assert env["schema"] == "aa-sdr-snapshot/v5"
    assert env["collected_components"] == ["metrics"]


def test_collected_components_is_top_level_not_nested() -> None:
    env = document_to_envelope(_doc(collected=("metrics",)))
    assert "collected_components" not in env["components"]


def test_degraded_family_in_full_capture_still_writes_v4() -> None:
    doc = _doc(fetch_status={"virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None)})
    env = document_to_envelope(doc)
    assert env["schema"] == "aa-sdr-snapshot/v4"
    assert "virtual_report_suites" in env["collected_components"]
    assert env["degraded_components"] == ["virtual_report_suites"]


def test_payload_reuse_gives_the_same_envelope() -> None:
    doc = _doc(collected=("metrics",))
    payload = doc.to_dict()
    snapshot_of_payload = copy.deepcopy(payload)
    assert document_to_envelope(doc, payload=payload) == document_to_envelope(doc)
    assert payload == snapshot_of_payload


def test_v5_fixture_matches_what_the_writer_produces(tmp_path: Path) -> None:
    """The checked-in fixture is the exact bytes a metrics-only capture writes."""
    path = save_snapshot(_doc(collected=("metrics",)), snapshot_dir=tmp_path)
    assert path.read_bytes() == V5_FIXTURE.read_bytes()


# --- reading -------------------------------------------------------------


def test_v5_fixture_validates_and_keeps_scope() -> None:
    env = _v5_env()
    validate_envelope(env)
    assert env["collected_components"] == ["metrics"]


def test_v5_without_collected_components_is_corrupt() -> None:
    env = _v5_env()
    del env["collected_components"]
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "metrics",
        {"metrics": True},
        ["metrics", "widgets"],
        ["metrics", "metrics"],
        ["metrics", 3],
    ],
    ids=["null", "string", "dict", "unknown-family", "duplicate", "non-string"],
)
def test_malformed_collected_components_is_corrupt(bad: object) -> None:
    env = _v5_env()
    env["collected_components"] = bad
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


def test_malformed_collected_components_on_v4_is_corrupt() -> None:
    env = document_to_envelope(_doc())
    env["collected_components"] = ["metrics", "widgets"]
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


def test_degraded_family_outside_scope_is_corrupt() -> None:
    env = _v5_env()
    env["degraded_components"] = ["classifications"]
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


def test_partial_family_outside_scope_is_corrupt() -> None:
    env = _v5_env()
    env["partial_components"] = {"virtual_report_suites": "minimal"}
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


@pytest.mark.parametrize("schema", ["aa-sdr-snapshot/v6", "aa-sdr-snapshot/v6.1", "aa-sdr-snapshot/v50"])
def test_v6_and_later_are_unsupported(schema: str) -> None:
    env = _v5_env()
    env["schema"] = schema
    with pytest.raises(SnapshotSchemaError, match="unsupported snapshot schema") as excinfo:
        validate_envelope(env)
    assert not isinstance(excinfo.value, SnapshotCorruptError)


def test_v5_minor_bump_is_accepted() -> None:
    env = _v5_env()
    env["schema"] = "aa-sdr-snapshot/v5.1"
    validate_envelope(env)


def test_legacy_v4_without_key_loads_as_unknown_scope() -> None:
    env = document_to_envelope(_doc())
    del env["collected_components"]
    validate_envelope(env)
    assert env.get("collected_components") is None


# --- round trips ---------------------------------------------------------


@pytest.mark.parametrize(
    "collected",
    [("metrics",), ("dimensions",), COMPONENT_FAMILIES],
    ids=["v5-metrics", "v5-dimensions", "v4-full"],
)
def test_round_trip_is_byte_stable(tmp_path: Path, collected: tuple[str, ...]) -> None:
    """Load a written snapshot, write the loaded envelope again: identical bytes."""
    path = save_snapshot(_doc(collected=collected), snapshot_dir=tmp_path)
    loaded = load_snapshot(path)
    again = tmp_path / "again.json"
    write_json(again, loaded)
    assert again.read_bytes() == path.read_bytes()


def test_round_trip_through_payload_reuse_is_byte_stable(tmp_path: Path) -> None:
    doc = _doc(collected=("metrics",))
    a = save_snapshot(doc, snapshot_dir=tmp_path / "a")
    b = save_snapshot(doc, snapshot_dir=tmp_path / "b", payload=doc.to_dict())
    assert a.read_bytes() == b.read_bytes()


def test_unknown_scope_document_writes_v4_without_inventing_scope() -> None:
    """A document whose scope is unknown never gains an inferred list."""
    env = document_to_envelope(_doc(collected=None))
    assert env["schema"] == "aa-sdr-snapshot/v4"
    assert "collected_components" not in env


def test_validation_does_not_add_scope_to_legacy_envelopes() -> None:
    """Unknown scope is the absent key; validation never invents one and is idempotent."""
    env = document_to_envelope(_doc())
    del env["collected_components"]
    before = copy.deepcopy(env)
    validate_envelope(env)
    validate_envelope(env)
    assert env == before


def test_validation_does_not_mutate_scoped_envelopes() -> None:
    env = _v5_env()
    before = copy.deepcopy(env)
    validate_envelope(env)
    assert env == before


def test_v4_with_null_collected_components_is_corrupt() -> None:
    env = document_to_envelope(_doc())
    env["collected_components"] = None
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


def test_v4_claiming_a_partial_scope_is_corrupt() -> None:
    """v4 means a full capture; older readers would read the gaps as deletions."""
    env = document_to_envelope(_doc())
    env["collected_components"] = ["metrics"]
    with pytest.raises(SnapshotCorruptError, match="collected_components"):
        validate_envelope(env)


def test_unknown_degraded_family_is_named_as_unknown() -> None:
    env = _v5_env()
    env["degraded_components"] = ["widgets"]
    with pytest.raises(SnapshotCorruptError, match="unknown family"):
        validate_envelope(env)
