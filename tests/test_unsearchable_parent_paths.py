"""Path checks under a directory the user can't search.

Before Python 3.14, `Path.exists()`, `is_dir()`, `is_file()`, and
`is_symlink()` raise `PermissionError` when a parent directory lacks search
permission; 3.14 returns False. `src/` uses the `os.path` forms, which return
False on every supported version, so these calls report "missing" instead of
crashing with a traceback. `tests/meta/test_no_raising_path_checks.py` keeps
the pathlib forms out of `src/`."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import ConfigError, SnapshotResolveError
from aa_auto_sdr.output.notion_registry import load_registry
from aa_auto_sdr.sdr.quality_policy import load_policy
from aa_auto_sdr.snapshot.resolver import resolve_snapshot
from aa_auto_sdr.snapshot.store import list_snapshots

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX directory permissions required")


@pytest.fixture
def locked(tmp_path: Path) -> Iterator[Path]:
    """A directory with mode 0o000, so nothing under it can be stat'ed."""
    d = tmp_path / "locked"
    d.mkdir()
    d.chmod(0o000)
    try:
        try:
            os.stat(d / "probe")
        except PermissionError:
            pass
        except FileNotFoundError:
            pytest.skip("environment does not enforce directory permissions (running as root?)")
        yield d
    finally:
        d.chmod(0o755)


def test_diff_path_token_reports_not_found(locked: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="snapshot file not found"):
        resolve_snapshot(str(locked / "a.json"), profile_snapshot_dir=None, repo_root=None)


def test_rsid_at_token_reports_no_snapshots(locked: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="no snapshots for rs1"):
        resolve_snapshot("rs1@latest", profile_snapshot_dir=locked / "snaps", repo_root=None)


def test_list_snapshots_returns_empty(locked: Path) -> None:
    assert list_snapshots(locked / "snaps") == []
    assert list_snapshots(locked / "snaps", rsid="rs1") == []


def test_profiles_report_missing(locked: Path) -> None:
    assert profiles.list_profiles(base=locked) == []
    with pytest.raises(ConfigError, match="Profile 'prod' not found"):
        profiles.read_profile("prod", base=locked)


def test_credential_sources_report_unmatched(monkeypatch: pytest.MonkeyPatch, locked: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    entries = credentials.resolution_chain(profile="prod", profiles_base=locked, working_dir=locked / "cwd")
    assert [e.matched for e in entries] == [False, False, False, False]
    with pytest.raises(ConfigError):
        credentials.resolve(working_dir=locked / "cwd")


def test_quality_policy_reports_not_found(locked: Path) -> None:
    with pytest.raises(ConfigError, match="--quality-policy file not found"):
        load_policy(locked / "policy.json")


def test_notion_registry_reads_as_empty(locked: Path) -> None:
    assert load_registry(locked / "registry.json") == {}
