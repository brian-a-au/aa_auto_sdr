"""Pipeline orchestration for single-RSID generation."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import OutputError
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.pipeline.models import RunResult

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return AaClient(handle=handle, company_id="testco")


def test_run_single_writes_excel_and_json(mock_client: AaClient, tmp_path: Path) -> None:
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["excel", "json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )
    assert isinstance(result, RunResult)
    assert result.rsid == "demo.prod"
    assert result.success is True
    assert {p.suffix for p in result.outputs} == {".xlsx", ".json"}
    for p in result.outputs:
        assert p.exists()


def test_run_single_default_filename_uses_rsid(mock_client: AaClient, tmp_path: Path) -> None:
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )
    [path] = result.outputs
    assert path.name == "demo.prod.json"


def test_run_single_populates_report_suite_name(mock_client: AaClient, tmp_path: Path) -> None:
    """The summary banner needs the friendly name; pipeline/single.py is the
    single source of truth (it's already built the SdrDocument)."""
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    # The fixture's report_suite has name="Demo Production".
    assert result.report_suite_name == "Demo Production"


def test_run_single_keeps_prior_success_when_later_format_fails(
    mock_client: AaClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    json_target = tmp_path / "demo.prod.json"
    markdown_target = tmp_path / "demo.prod.md"
    json_target.write_bytes(b"old json")
    markdown_target.write_bytes(b"old markdown")
    real_replace = os.replace

    def fail_markdown_replace(source: Path, destination: Path) -> None:
        if destination.suffix == ".md":
            raise PermissionError("markdown destination locked")
        real_replace(source, destination)

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_markdown_replace)

    with pytest.raises(OutputError, match="markdown destination locked") as error:
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json", "markdown"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.21.12",
        )

    assert "demo.prod" in str(error.value)
    assert str(markdown_target) in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)
    assert json.loads(json_target.read_text())["tool_version"] == "1.21.12"
    assert markdown_target.read_bytes() == b"old markdown"
    assert [path for path in tmp_path.iterdir() if path.name.startswith(".")] == []


@pytest.mark.parametrize(
    ("formats", "snapshot", "conversions"),
    [
        (["json"], True, 1),
        (["json"], False, 1),
        ([], True, 1),
        (["markdown"], False, 0),
        (["excel", "csv", "json", "html", "markdown"], True, 1),
    ],
)
def test_payload_conversion_and_output_parity(mock_client, tmp_path, monkeypatch, formats, snapshot, conversions):
    from aa_auto_sdr.core.json_io import write_json
    from aa_auto_sdr.sdr.document import SdrDocument
    from aa_auto_sdr.snapshot.schema import document_to_envelope

    documents = []
    payloads = []
    real = SdrDocument.to_dict

    def count(doc):
        documents.append(doc)
        payload = real(doc)
        payloads.append(payload)
        return payload

    monkeypatch.setattr(SdrDocument, "to_dict", count)
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=formats,
        output_dir=tmp_path / "outputs",
        snapshot_dir=tmp_path / "snapshots" if snapshot else None,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="test",
        audit_naming=True,
        flag_stale=True,
    )
    assert len(documents) == conversions
    if "json" in formats:
        from aa_auto_sdr.sdr.definitions import enrich_payload

        expected = real(documents[0])
        expected_path = tmp_path / "expected.json"
        write_json(expected_path, enrich_payload(documents[0], expected))
        assert (tmp_path / "outputs/demo.prod.json").read_bytes() == expected_path.read_bytes()
        assert payloads[0] == expected  # envelope promotion must not mutate the shared payload
    if snapshot:
        expected = document_to_envelope(documents[0], payload=real(documents[0]))
        expected_path = tmp_path / "envelope.json"
        write_json(expected_path, expected)
        assert result.outputs[-1].read_bytes() == expected_path.read_bytes()


@pytest.mark.parametrize("failure", ["json", "snapshot"])
def test_payload_write_failure_order(mock_client, tmp_path, monkeypatch, failure):
    from aa_auto_sdr.core.exceptions import OutputError

    output = tmp_path / "output"
    snapshots = tmp_path / "snapshots"
    real_replace = os.replace

    def fail_replace(source, destination):
        if (failure == "json" and destination.parent == output) or (
            failure == "snapshot" and snapshots in destination.parents
        ):
            raise PermissionError("locked")
        real_replace(source, destination)

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)
    with pytest.raises((PermissionError, OutputError), match="locked"):
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json"],
            output_dir=output,
            snapshot_dir=snapshots,
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="test",
        )
    assert (output / "demo.prod.json").exists() == (failure == "snapshot")
    assert not list(snapshots.rglob("*.json"))


@pytest.mark.parametrize("subclass", [False, True])
def test_custom_json_writer_preserves_write(mock_client, tmp_path, monkeypatch, subclass):
    from aa_auto_sdr.output.writers.json import JsonWriter

    calls = []

    class Custom(JsonWriter if subclass else object):
        extension = ".json"

        def write(self, doc, path):
            calls.append(doc.report_suite.rsid)
            path.write_text("custom")
            return [path]

    single.registry.bootstrap()
    monkeypatch.setitem(single.registry._WRITERS, "json", Custom())
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        snapshot_dir=tmp_path / "snapshots",
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="test",
    )
    assert calls == ["demo.prod"]
    assert result.outputs[0].read_text() == "custom"
    assert json.loads(result.outputs[1].read_text())["rsid"] == "demo.prod"


def test_parallel_payloads_are_run_local(mock_client, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Barrier

    from aa_auto_sdr.sdr.builder import build_sdr
    from aa_auto_sdr.snapshot import store

    doc = build_sdr(mock_client, "demo.prod", captured_at=datetime(2026, 4, 25, tzinfo=UTC), tool_version="test")
    monkeypatch.setattr(
        single,
        "build_sdr",
        lambda _client, rsid, **_kwargs: replace(doc, report_suite=replace(doc.report_suite, rsid=rsid)),
    )
    barrier = Barrier(2)
    save = store.save_snapshot

    def synchronized_save(doc, **kwargs):
        barrier.wait(timeout=10)
        assert kwargs["payload"]["report_suite"]["rsid"] == doc.report_suite.rsid
        return save(doc, **kwargs)

    monkeypatch.setattr(store, "save_snapshot", synchronized_save)

    def run(rsid):
        return single.run_single(
            client=mock_client,
            rsid=rsid,
            formats=["json"],
            output_dir=tmp_path,
            snapshot_dir=tmp_path / "snapshots",
            captured_at=doc.captured_at,
            tool_version="test",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["a", "b"]))
    for result in results:
        assert json.loads(result.outputs[0].read_text())["report_suite"]["rsid"] == result.rsid
        assert json.loads(result.outputs[1].read_text())["rsid"] == result.rsid


def test_output_directory_failure_is_contextual(mock_client, tmp_path):
    output_dir = tmp_path / "not-a-directory"
    output_dir.write_text("existing file")

    with pytest.raises(OutputError) as error:
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json"],
            output_dir=output_dir,
            captured_at=datetime(2026, 10, 17, tzinfo=UTC),
            tool_version="test",
        )

    assert "demo.prod" in str(error.value)
    assert str(output_dir) in str(error.value)
    assert isinstance(error.value.__cause__, OSError)
    assert output_dir.read_text() == "existing file"


def test_retained_json_write_failure_is_contextual(mock_client, tmp_path, monkeypatch):
    target = tmp_path / "demo.prod.json"
    target.write_text("previous capture")
    snapshot_dir = tmp_path / "snapshots"

    def fail_replace(source, destination):
        raise PermissionError("destination locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)
    with pytest.raises(OutputError, match="destination locked") as error:
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json"],
            output_dir=tmp_path,
            snapshot_dir=snapshot_dir,
            captured_at=datetime(2026, 10, 17, tzinfo=UTC),
            tool_version="test",
        )

    assert "json" in str(error.value)
    assert str(target) in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)
    assert target.read_text() == "previous capture"
    assert not snapshot_dir.exists()
    assert not list(tmp_path.glob(".*"))


@pytest.mark.parametrize("quality_format", ["json", "csv"])
def test_quality_report_failure_keeps_sdr_output(mock_client, tmp_path, monkeypatch, quality_format):
    target = tmp_path / f"quality_report_demo.prod_20261017T000000.{quality_format}"
    target.write_text("previous quality report")
    real_replace = os.replace

    def fail_quality_replace(source, destination):
        if destination == target:
            raise PermissionError("quality destination locked")
        real_replace(source, destination)

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_quality_replace)
    with pytest.raises(OutputError, match="quality destination locked") as error:
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 10, 17, tzinfo=UTC),
            tool_version="test",
            audit_naming=True,
            quality_report=quality_format,
        )

    assert "demo.prod" in str(error.value)
    assert str(target) in str(error.value)
    assert isinstance(error.value.__cause__, PermissionError)
    assert target.read_text() == "previous quality report"
    assert json.loads((tmp_path / "demo.prod.json").read_text())["tool_version"] == "test"
    assert not list(tmp_path.glob(".*"))


@pytest.mark.parametrize("exception", [RuntimeError("writer bug"), OutputError("already classified")])
def test_non_os_writer_errors_pass_through(mock_client, tmp_path, monkeypatch, exception):
    from aa_auto_sdr.output.writers.json import JsonWriter

    def fail_write(self, doc, output_path):
        raise exception

    monkeypatch.setattr(JsonWriter, "write", fail_write)
    with pytest.raises(type(exception)) as error:
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 10, 17, tzinfo=UTC),
            tool_version="test",
        )
    assert error.value is exception
