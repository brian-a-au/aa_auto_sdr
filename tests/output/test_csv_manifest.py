"""CSV staged publication and the `<stem>._manifest.json` completion manifest.

All section files are rendered into a hidden staging directory next to the
target, then published together, ending with the manifest. A failure while
rendering leaves the previously published files untouched, and files that are
not part of the new run are never deleted."""

from __future__ import annotations

import csv as _csv
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

import aa_auto_sdr.output.writers.csv as csvmod
from aa_auto_sdr.api import models as m
from aa_auto_sdr.output.writers.csv import CsvWriter
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, SdrDocument

_DIMENSIONS = [
    m.Dimension(
        id=f"variables/evar{i}",
        name=f"Dim {i}",
        type="string",
        category=None,
        parent="",
        pathable=False,
        description=None,
    )
    for i in (1, 2, 3)
]

_SECTIONS = [
    ("summary", "Summary"),
    ("coverage", "Coverage"),
    ("dimensions", "Dimensions"),
    ("metrics", "Metrics"),
    ("segments", "Segments"),
    ("calculated_metrics", "Calculated Metrics"),
    ("virtual_report_suites", "Virtual Report Suites"),
    ("classifications", "Classifications"),
    ("references", "References"),
]


def _doc(rsid: str = "demo.prod", **overrides) -> SdrDocument:
    base = SdrDocument(
        report_suite=m.ReportSuite(rsid=rsid, name="Demo", timezone=None, currency=None, parent_rsid=None),
        dimensions=list(_DIMENSIONS),
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


def _audited() -> dict:
    return {
        "issues": [{"severity": "LOW", "category": "naming", "type": "dimensions", "item_id": "x", "item_name": ""}],
        "summary": {"by_severity": {"LOW": 1}, "total": 1, "verdict": "n/a"},
    }


def _manifest(directory: Path, stem: str = "demo.prod") -> dict:
    return json.loads((directory / f"{stem}._manifest.json").read_text(encoding="utf-8"))


def test_manifest_is_written_last_and_returned(tmp_path: Path) -> None:
    paths = CsvWriter().write(_doc(), tmp_path / "demo.prod.csv")
    assert paths[-1] == tmp_path / "demo.prod._manifest.json"
    assert len(paths) == 10


def test_manifest_shape_and_entries(tmp_path: Path) -> None:
    CsvWriter().write(_doc(), tmp_path / "demo.prod.csv")
    manifest = _manifest(tmp_path)
    assert manifest["manifest_version"] == "1.0"
    assert manifest["complete"] is True
    assert datetime.fromisoformat(manifest["generated_at"]).tzinfo is not None
    assert [(f["name"], f["sheet"]) for f in manifest["files"]] == [
        (f"demo.prod.{key}.csv", sheet) for key, sheet in _SECTIONS
    ]
    for entry in manifest["files"]:
        assert set(entry) == {"name", "sheet", "sha256", "rows", "bytes"}


def test_manifest_sha256_bytes_and_rows_match_files(tmp_path: Path) -> None:
    CsvWriter().write(_doc(quality=_audited()), tmp_path / "demo.prod.csv")
    entries = {f["name"]: f for f in _manifest(tmp_path)["files"]}
    assert "demo.prod.quality_issues.csv" in entries
    for name, entry in entries.items():
        data = (tmp_path / name).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["bytes"] == len(data)
        with (tmp_path / name).open(encoding="utf-8-sig", newline="") as fh:
            data_rows = list(_csv.reader(fh))[1:]
        assert entry["rows"] == len(data_rows)
    assert entries["demo.prod.dimensions.csv"]["rows"] == 3
    assert entries["demo.prod.metrics.csv"]["rows"] == 0
    assert entries["demo.prod.coverage.csv"]["rows"] == 6
    assert entries["demo.prod.quality_issues.csv"]["rows"] == 1


def test_no_staging_leftovers(tmp_path: Path) -> None:
    CsvWriter().write(_doc(), tmp_path / "demo.prod.csv")
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_render_failure_leaves_previous_files_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = CsvWriter()
    writer.write(_doc(), tmp_path / "demo.prod.csv")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    real = csvmod._encode_csv
    calls = {"n": 0}

    def flaky(headers, rows):
        calls["n"] += 1
        if calls["n"] == 5:  # fail mid-bundle, after several sections rendered
            raise RuntimeError("section render failed")
        return real(headers, rows)

    monkeypatch.setattr(csvmod, "_encode_csv", flaky)
    with pytest.raises(RuntimeError, match="section render failed"):
        writer.write(_doc(dimensions=[_DIMENSIONS[0]], quality=_audited()), tmp_path / "demo.prod.csv")

    after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert after == before  # same files, same bytes, no staging dir left


def test_publish_failure_leaves_no_manifest_and_no_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = CsvWriter()
    writer.write(_doc(), tmp_path / "demo.prod.csv")
    real = csvmod.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr(csvmod.os, "replace", flaky)
    with pytest.raises(OSError, match="disk full"):
        writer.write(_doc(), tmp_path / "demo.prod.csv")
    # Without a manifest a consumer knows the set is not a complete bundle.
    assert not (tmp_path / "demo.prod._manifest.json").exists()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


def test_unrelated_and_stale_files_are_never_deleted(tmp_path: Path) -> None:
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("keep me", encoding="utf-8")
    writer = CsvWriter()
    writer.write(_doc(quality=_audited()), tmp_path / "demo.prod.csv")
    # Second run has no audit, so quality_issues.csv is not part of it.
    writer.write(_doc(), tmp_path / "demo.prod.csv")
    assert unrelated.read_text(encoding="utf-8") == "keep me"
    assert (tmp_path / "demo.prod.quality_issues.csv").exists()
    names = [f["name"] for f in _manifest(tmp_path)["files"]]
    assert "demo.prod.quality_issues.csv" not in names


def test_batch_into_one_directory_keeps_one_manifest_per_rsid(tmp_path: Path) -> None:
    writer = CsvWriter()
    for rsid in ("rs.one", "rs.two"):
        writer.write(_doc(rsid=rsid), tmp_path / f"{rsid}.csv")
    for rsid in ("rs.one", "rs.two"):
        manifest = _manifest(tmp_path, rsid)
        assert all(f["name"].startswith(f"{rsid}.") for f in manifest["files"])
        for f in manifest["files"]:
            assert hashlib.sha256((tmp_path / f["name"]).read_bytes()).hexdigest() == f["sha256"]


def test_parallel_writes_into_one_directory(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    rsids = [f"rs{i}" for i in range(8)]
    writer = CsvWriter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda r: writer.write(_doc(rsid=r), tmp_path / f"{r}.csv"), rsids))
    for rsid in rsids:
        assert len(_manifest(tmp_path, rsid)["files"]) == 9
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []
