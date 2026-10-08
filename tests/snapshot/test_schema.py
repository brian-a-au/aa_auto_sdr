"""snapshot/schema.py — envelope build + validate."""

from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api import models as api_models
from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot.schema import (
    SCHEMA_VERSION,
    document_to_envelope,
    validate_envelope,
)


def _stub_doc() -> SdrDocument:
    rs = api_models.ReportSuite(
        rsid="demo.prod",
        name="Demo Production",
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )
    return SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 26, 17, 29, 1, tzinfo=UTC),
        tool_version="0.7.0",
    )


def test_schema_version_is_v4() -> None:
    assert SCHEMA_VERSION == "aa-sdr-snapshot/v4"


def test_document_to_envelope_shape() -> None:
    env = document_to_envelope(_stub_doc())
    assert env["schema"] == SCHEMA_VERSION
    assert env["rsid"] == "demo.prod"
    assert env["captured_at"] == "2026-04-26T17:29:01+00:00"
    assert env["tool_version"] == "0.7.0"
    assert "components" in env
    assert "report_suite" in env["components"]
    assert "dimensions" in env["components"]
    # Header fields must NOT also appear nested under components
    assert "captured_at" not in env["components"]
    assert "tool_version" not in env["components"]
    assert env["degraded_components"] == []
    assert env["partial_components"] == {}


def test_validate_envelope_accepts_well_formed() -> None:
    env = document_to_envelope(_stub_doc())
    validate_envelope(env)  # should not raise


def test_validate_envelope_rejects_missing_schema() -> None:
    env = document_to_envelope(_stub_doc())
    del env["schema"]
    with pytest.raises(SnapshotSchemaError, match="missing required key"):
        validate_envelope(env)


def test_validate_envelope_rejects_unknown_major() -> None:
    env = document_to_envelope(_stub_doc())
    env["schema"] = "aa-sdr-snapshot/v999"
    with pytest.raises(SnapshotSchemaError, match="v999"):
        validate_envelope(env)


def test_validate_envelope_accepts_minor_bump() -> None:
    """v1.x is forward-compat: validate accepts v1.1, v1.2, etc."""
    env = document_to_envelope(_stub_doc())
    env["schema"] = "aa-sdr-snapshot/v1.5"
    validate_envelope(env)  # should not raise


def test_validate_envelope_rejects_missing_required_keys() -> None:
    env = document_to_envelope(_stub_doc())
    del env["rsid"]
    with pytest.raises(SnapshotSchemaError, match="rsid"):
        validate_envelope(env)


def test_validate_envelope_rejects_naive_timestamp() -> None:
    """§5.2: only timezone-aware ISO-8601 timestamps accepted."""
    env = document_to_envelope(_stub_doc())
    env["captured_at"] = "2026-04-26T17:29:01"  # no offset
    with pytest.raises(SnapshotSchemaError, match=r"naive|timezone|offset"):
        validate_envelope(env)


def test_v3_envelope_loads_on_v1_12_0() -> None:
    """v3 envelopes (no v4 inner keys) still load — defaulted in-memory."""
    env = document_to_envelope(_stub_doc())
    # Simulate a v3-shaped envelope: schema string + quality block missing v4 keys.
    env["schema"] = "aa-sdr-snapshot/v3"
    env["quality"] = {"naming_audit": {"total_components": 0}, "stale_components": []}
    validate_envelope(env)  # in-memory defaults populate v4 keys
    assert env["quality"]["issues"] == []
    assert env["quality"]["summary"] == {"by_severity": {}, "total": 0, "verdict": "n/a"}


def test_v4_envelope_round_trips() -> None:
    """v4 envelopes carry quality.issues + quality.summary verbatim."""
    env = document_to_envelope(_stub_doc())
    # Inject a populated quality block.
    env["quality"] = {
        "naming_audit": {"total_components": 1},
        "stale_components": [],
        "issues": [
            {
                "severity": "MEDIUM",
                "category": "stale",
                "type": "stale_keyword",
                "item_id": "evar5",
                "item_name": "v_old",
                "issue": "Component name matches stale_keyword pattern: old",
                "details": {},
            },
        ],
        "summary": {"by_severity": {"MEDIUM": 1}, "total": 1, "verdict": "fail", "policy_threshold": "MEDIUM"},
    }
    validate_envelope(env)
    assert env["quality"]["summary"]["verdict"] == "fail"
    assert env["quality"]["issues"][0]["severity"] == "MEDIUM"


def test_validate_envelope_rejects_unparseable_timestamp_with_offset_shape() -> None:
    """A captured_at that merely *ends* in an offset must still parse as a real
    ISO-8601 timestamp — otherwise trending crashes later at fromisoformat."""
    env = document_to_envelope(_stub_doc())
    env["captured_at"] = "garbage+00:00"
    with pytest.raises(SnapshotSchemaError, match=r"timezone-aware ISO-8601"):
        validate_envelope(env)


@pytest.mark.parametrize("root", [None, [], "snapshot", 12, {}])
def test_non_mapping_root_is_corrupt(root) -> None:
    from aa_auto_sdr.core.exceptions import SnapshotCorruptError

    with pytest.raises(SnapshotCorruptError):
        validate_envelope(root)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema",), None),
        (("components",), []),
        (("components", "report_suite"), None),
        (("components", "metrics"), {}),
        (("components", "dimensions"), [None]),
        (("quality",), []),
        (("quality", "naming_audit"), []),
        (("quality", "stale_components"), [None]),
        (("quality", "issues"), {}),
        (("quality", "summary"), []),
        (("quality", "summary", "by_severity"), []),
        (("degraded_components",), {}),
        (("partial_components",), []),
        (("captured_at",), "garbage+00:00"),
    ],
)
def test_malformed_containers_are_corrupt_without_defaulting(path, value) -> None:
    from copy import deepcopy

    from aa_auto_sdr.core.exceptions import SnapshotCorruptError

    env = document_to_envelope(_stub_doc())
    env["quality"] = {}
    target = env
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value
    before = deepcopy(env)
    with pytest.raises(SnapshotCorruptError):
        validate_envelope(env)
    assert env == before


@pytest.mark.parametrize("schema", ["aa-sdr-snapshot/v5", "foreign/v1"])
def test_unsupported_string_schema_is_not_corruption(schema) -> None:
    from aa_auto_sdr.core.exceptions import SnapshotCorruptError

    with pytest.raises(SnapshotSchemaError) as caught:
        validate_envelope({"schema": schema, "components": []})
    assert not isinstance(caught.value, SnapshotCorruptError)


@pytest.mark.parametrize("major", [1, 2, 3, 4])
@pytest.mark.parametrize("minor", ["", ".12"])
def test_minimal_legacy_envelopes_keep_loading(major, minor) -> None:
    env = document_to_envelope(_stub_doc())
    env["schema"] = f"aa-sdr-snapshot/v{major}{minor}"
    env["components"] = {}
    del env["quality"]
    if major == 1:
        del env["degraded_components"]
        del env["partial_components"]
    validate_envelope(env)
    assert env["components"] == {}
    assert env["quality"] is None
