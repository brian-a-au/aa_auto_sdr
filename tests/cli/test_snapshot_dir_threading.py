"""Tests for the shared --snapshot-dir resolver.

This module pins the resolver precedence (--snapshot-dir > profile > "default")
across generate/batch/watch dispatch. Lives in tests/cli/ because the resolver
is a CLI-layer helper that reads argparse Namespaces.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _ns(**kwargs) -> argparse.Namespace:
    """Build a Namespace with the keys the resolver reads. Anything not set
    falls back via getattr(..., None)."""
    return argparse.Namespace(**kwargs)


class TestResolveSnapshotDir:
    def test_explicit_snapshot_dir_wins(self, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands._shared import resolve_snapshot_dir

        explicit = tmp_path / "explicit"
        ns = _ns(snapshot_dir=str(explicit), profile="acme")
        assert resolve_snapshot_dir(ns) == Path(explicit)

    def test_profile_used_when_no_snapshot_dir(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import _shared
        from aa_auto_sdr.core import profiles

        monkeypatch.setattr(profiles, "default_base", lambda: tmp_path / ".aa")
        ns = _ns(snapshot_dir=None, profile="acme")
        assert _shared.resolve_snapshot_dir(ns) == tmp_path / ".aa" / "orgs" / "acme" / "snapshots"

    def test_default_profile_when_neither_set(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import _shared
        from aa_auto_sdr.core import profiles

        monkeypatch.setattr(profiles, "default_base", lambda: tmp_path / ".aa")
        ns = _ns(snapshot_dir=None, profile=None)
        assert _shared.resolve_snapshot_dir(ns) == tmp_path / ".aa" / "orgs" / "default" / "snapshots"
