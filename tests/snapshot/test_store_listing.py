"""Tests for snapshot.store list_snapshots / prune_snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aa_auto_sdr.snapshot.retention import RetentionPolicy
from aa_auto_sdr.snapshot.store import (
    list_snapshots,
    prune_snapshots,
)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    return path


@pytest.fixture
def populated_dir(tmp_path: Path) -> Path:
    """Build a snapshot dir with two RSIDs, three snapshots each."""
    base = tmp_path / "snapshots"
    for rsid in ("RS1", "RS2"):
        for day in ("20", "21", "22"):
            _touch(base / rsid / f"2026-04-{day}T10-00-00+00-00.json")
    return base


class TestListSnapshots:
    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert list_snapshots(tmp_path / "missing") == []

    def test_lists_all_when_no_rsid(self, populated_dir: Path) -> None:
        files = list_snapshots(populated_dir)
        assert len(files) == 6

    def test_lists_one_rsid_when_filtered(self, populated_dir: Path) -> None:
        files = list_snapshots(populated_dir, rsid="RS1")
        assert len(files) == 3
        assert all("RS1" in str(p) for p in files)

    def test_unknown_rsid_returns_empty(self, populated_dir: Path) -> None:
        assert list_snapshots(populated_dir, rsid="UNKNOWN") == []

    def test_results_are_sorted_chronologically(self, populated_dir: Path) -> None:
        files = list_snapshots(populated_dir, rsid="RS1")
        names = [p.name for p in files]
        assert names == sorted(names)


class TestPruneSnapshots:
    def test_dry_run_does_not_unlink(self, populated_dir: Path) -> None:
        policy = RetentionPolicy(keep_last=1)
        deleted = prune_snapshots(populated_dir, policy, dry_run=True)
        # Both RSIDs lose 2 each
        assert len(deleted) == 4
        # Files still exist
        assert all(p.exists() for p in deleted)

    def test_per_rsid_keep_last(self, populated_dir: Path) -> None:
        policy = RetentionPolicy(keep_last=1)
        deleted = prune_snapshots(populated_dir, policy)
        assert len(deleted) == 4
        # The one most recent of each RSID survives
        survivors = list_snapshots(populated_dir)
        assert len(survivors) == 2
        assert {p.parent.name for p in survivors} == {"RS1", "RS2"}

    def test_filtered_to_one_rsid(self, populated_dir: Path) -> None:
        policy = RetentionPolicy(keep_last=1)
        prune_snapshots(populated_dir, policy, rsid="RS1")
        # RS1 has 1 left, RS2 still has 3
        assert len(list_snapshots(populated_dir, rsid="RS1")) == 1
        assert len(list_snapshots(populated_dir, rsid="RS2")) == 3

    def test_inactive_policy_no_delete(self, populated_dir: Path) -> None:
        deleted = prune_snapshots(populated_dir, RetentionPolicy())
        assert deleted == []
        assert len(list_snapshots(populated_dir)) == 6

    def test_keep_since_with_now_injection(self, populated_dir: Path) -> None:
        # Pretend it's 2026-04-23 — anything older than 1 day goes
        now = datetime(2026, 4, 23, 9, 0, 0, tzinfo=UTC)
        policy = RetentionPolicy(keep_since=timedelta(days=1))
        deleted = prune_snapshots(populated_dir, policy, now=now)
        # 04-22 is within 1 day; 04-20 and 04-21 are not — 2 per RSID
        assert len(deleted) == 4
