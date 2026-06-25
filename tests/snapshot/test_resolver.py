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


def test_resolve_directory_path_raises_resolve_error(tmp_path: Path) -> None:
    """Passing a directory must surface as SnapshotResolveError, not a stack trace."""
    with pytest.raises(SnapshotResolveError, match=r"directory"):
        resolve_snapshot(str(tmp_path), profile_snapshot_dir=None, repo_root=None)


def test_resolve_bare_token_uses_spec_message(tmp_path: Path) -> None:
    """Spec §4: bare tokens that match no form get a multi-form error message."""
    with pytest.raises(
        SnapshotResolveError,
        match=r"could not interpret 'nonsense'",
    ):
        resolve_snapshot("nonsense", profile_snapshot_dir=None, repo_root=None)


def test_resolve_git_token_missing_path_part_raises(tmp_path: Path) -> None:
    """`git:HEAD:` (empty path) and `git::path` (empty ref) parse as malformed."""
    with pytest.raises(SnapshotResolveError, match="git:"):
        resolve_snapshot("git:HEAD:", profile_snapshot_dir=None, repo_root=tmp_path)
    with pytest.raises(SnapshotResolveError, match="git:"):
        resolve_snapshot("git::path.json", profile_snapshot_dir=None, repo_root=tmp_path)


# --- helper-level + dispatch error-path coverage ---------------------------


def test_resolve_path_helper_missing_raises() -> None:
    """_resolve_path guards a non-existent path even though _dispatch only
    calls it for existing paths (defensive)."""
    from aa_auto_sdr.snapshot import resolver

    with pytest.raises(SnapshotResolveError, match="not found"):
        resolver._resolve_path(Path("/nonexistent/snap.json"))


def test_resolve_existing_path_with_invalid_json_raises(tmp_path: Path) -> None:
    """An existing file that is not valid JSON → SnapshotResolveError, not a raw
    JSONDecodeError leaking out."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    with pytest.raises(SnapshotResolveError, match="not valid JSON"):
        resolve_snapshot(str(bad), profile_snapshot_dir=None, repo_root=None)


def test_resolve_path_helper_oserror_raises(tmp_path: Path, monkeypatch) -> None:
    """An OSError while reading a present snapshot is wrapped as SnapshotResolveError."""
    from aa_auto_sdr.snapshot import resolver

    snap = tmp_path / "x.json"
    _write_snapshot(snap, "demo.prod", "2026-04-26T17:29:01+00:00")

    def _boom(_path):
        raise OSError("disk gone")

    monkeypatch.setattr(resolver, "read_json", _boom)
    with pytest.raises(SnapshotResolveError, match="could not read"):
        resolver._resolve_path(snap)


def test_resolve_rsid_at_empty_spec_raises(tmp_path: Path) -> None:
    """`<rsid>@` with no spec → parse error."""
    with pytest.raises(SnapshotResolveError, match="<rsid>@<spec>"):
        resolve_snapshot("demo.prod@", profile_snapshot_dir=tmp_path, repo_root=None)


def test_resolve_rsid_at_missing_timestamp_raises(tmp_path: Path) -> None:
    """An exact timestamp that has no matching file → not found."""
    _write_snapshot(tmp_path / "demo.prod" / "2026-04-26T17-29-01+00-00.json", "demo.prod", "2026-04-26T17:29:01+00:00")
    with pytest.raises(SnapshotResolveError, match="not found"):
        resolve_snapshot("demo.prod@2099-01-01T00-00-00", profile_snapshot_dir=tmp_path, repo_root=None)


def test_resolve_git_non_json_raises(tmp_path: Path, monkeypatch) -> None:
    """`git show` content that isn't JSON → SnapshotResolveError."""
    from aa_auto_sdr.snapshot import resolver

    monkeypatch.setattr(resolver, "git_show", lambda **_kw: "not json at all")
    with pytest.raises(SnapshotResolveError, match="did not decode as JSON"):
        resolve_snapshot("git:HEAD:snap.json", profile_snapshot_dir=None, repo_root=tmp_path)


def test_resolve_rsid_at_unknown_rsid_dir_raises(tmp_path: Path) -> None:
    """An rsid whose snapshot subdir does not exist under the profile dir → error."""
    with pytest.raises(SnapshotResolveError, match="no snapshots for"):
        resolve_snapshot("ghost.rsid@latest", profile_snapshot_dir=tmp_path, repo_root=None)
