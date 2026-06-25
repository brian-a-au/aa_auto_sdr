"""snapshot.store — coverage for filename passthrough and missing-dir paths."""

from __future__ import annotations

from pathlib import Path

from aa_auto_sdr.snapshot.retention import RetentionPolicy
from aa_auto_sdr.snapshot.store import filename_to_captured_at, prune_snapshots


def test_filename_to_captured_at_passes_through_without_t() -> None:
    """A stem with no 'T' separator is not a recognized timestamp — pass through."""
    assert filename_to_captured_at("plain-name") == "plain-name"


def test_filename_to_captured_at_best_effort_when_no_offset_signal() -> None:
    """A 'T'-bearing stem too short to carry an offset converts all hyphens."""
    assert filename_to_captured_at("2026-04-26T17-30") == "2026-04-26T17:30"


def test_prune_snapshots_on_missing_dir_returns_empty(tmp_path: Path) -> None:
    """Cross-RSID prune over a non-existent dir: _list_rsids returns []."""
    deleted = prune_snapshots(tmp_path / "missing", RetentionPolicy(keep_last=1))
    assert deleted == []
