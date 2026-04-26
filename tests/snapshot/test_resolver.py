"""snapshot/resolver.py — token dispatcher (path / @ts / @latest / @previous / git:)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError, SnapshotSchemaError
from aa_auto_sdr.snapshot.resolver import resolve_snapshot


def _write_snapshot(path: Path, rsid: str, captured_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "aa-sdr-snapshot/v1",
                "rsid": rsid,
                "captured_at": captured_at,
                "tool_version": "0.7.0",
                "components": {
                    "report_suite": {"rsid": rsid, "name": rsid},
                    "dimensions": [],
                    "metrics": [],
                    "segments": [],
                    "calculated_metrics": [],
                    "virtual_report_suites": [],
                    "classifications": [],
                },
            },
            sort_keys=True,
        )
    )


def test_resolve_path_returns_envelope(tmp_path: Path) -> None:
    snap = tmp_path / "x.json"
    _write_snapshot(snap, "demo.prod", "2026-04-26T17:29:01+00:00")
    env = resolve_snapshot(str(snap), profile_snapshot_dir=None, repo_root=None)
    assert env["rsid"] == "demo.prod"


def test_resolve_path_missing_raises_resolve_error(tmp_path: Path) -> None:
    with pytest.raises(SnapshotResolveError):
        resolve_snapshot(str(tmp_path / "nope.json"), profile_snapshot_dir=None, repo_root=None)


def test_resolve_rsid_at_timestamp(tmp_path: Path) -> None:
    snap = tmp_path / "demo.prod" / "2026-04-26T17-29-01+00-00.json"
    _write_snapshot(snap, "demo.prod", "2026-04-26T17:29:01+00:00")
    env = resolve_snapshot(
        "demo.prod@2026-04-26T17-29-01+00-00",
        profile_snapshot_dir=tmp_path,
        repo_root=None,
    )
    assert env["captured_at"] == "2026-04-26T17:29:01+00:00"


def test_resolve_rsid_at_latest(tmp_path: Path) -> None:
    rs_dir = tmp_path / "demo.prod"
    _write_snapshot(rs_dir / "2026-04-20T10-00-00+00-00.json", "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_snapshot(rs_dir / "2026-04-26T17-29-01+00-00.json", "demo.prod", "2026-04-26T17:29:01+00:00")
    env = resolve_snapshot("demo.prod@latest", profile_snapshot_dir=tmp_path, repo_root=None)
    assert env["captured_at"] == "2026-04-26T17:29:01+00:00"


def test_resolve_rsid_at_previous(tmp_path: Path) -> None:
    rs_dir = tmp_path / "demo.prod"
    _write_snapshot(rs_dir / "2026-04-20T10-00-00+00-00.json", "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_snapshot(rs_dir / "2026-04-26T17-29-01+00-00.json", "demo.prod", "2026-04-26T17:29:01+00:00")
    env = resolve_snapshot("demo.prod@previous", profile_snapshot_dir=tmp_path, repo_root=None)
    assert env["captured_at"] == "2026-04-20T10:00:00+00:00"


def test_resolve_rsid_at_previous_with_only_one_snapshot_raises(tmp_path: Path) -> None:
    rs_dir = tmp_path / "demo.prod"
    _write_snapshot(rs_dir / "2026-04-26T17-29-01+00-00.json", "demo.prod", "2026-04-26T17:29:01+00:00")
    with pytest.raises(SnapshotResolveError, match=r"at least two|previous"):
        resolve_snapshot("demo.prod@previous", profile_snapshot_dir=tmp_path, repo_root=None)


def test_resolve_at_token_without_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="profile"):
        resolve_snapshot("demo.prod@latest", profile_snapshot_dir=None, repo_root=None)


def test_resolve_rsid_at_latest_empty_dir_raises(tmp_path: Path) -> None:
    (tmp_path / "demo.prod").mkdir()
    with pytest.raises(SnapshotResolveError, match="no snapshots"):
        resolve_snapshot("demo.prod@latest", profile_snapshot_dir=tmp_path, repo_root=None)


def test_resolve_git_token(tmp_path: Path) -> None:
    """Real git repo with one tracked snapshot."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    snap = tmp_path / "snap.json"
    _write_snapshot(snap, "demo.prod", "2026-04-26T17:29:01+00:00")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=tmp_path, check=True)
    env = resolve_snapshot("git:HEAD:snap.json", profile_snapshot_dir=None, repo_root=tmp_path)
    assert env["rsid"] == "demo.prod"


def test_resolve_unknown_token_raises(tmp_path: Path) -> None:
    with pytest.raises(SnapshotResolveError):
        resolve_snapshot("nonsense", profile_snapshot_dir=None, repo_root=None)


def test_resolve_invalid_envelope_raises_schema_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": "aa-sdr-snapshot/v999"}')
    with pytest.raises(SnapshotSchemaError):
        resolve_snapshot(str(bad), profile_snapshot_dir=None, repo_root=None)
