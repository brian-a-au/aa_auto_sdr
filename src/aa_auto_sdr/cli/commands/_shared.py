"""Shared helpers for CLI command modules.

Currently exposes `resolve_snapshot_dir`, originally defined in
`cli/commands/watch.py` and used only by the watch driver. v1.15.1 promotes
it to a shared helper so `generate` and `batch` can honor `--snapshot-dir`
uniformly — closing a deferral from v1.15.0 (Codex P3).
"""

from __future__ import annotations

import argparse
from pathlib import Path


def resolve_snapshot_dir(ns: argparse.Namespace) -> Path:
    """Pick the snapshot directory: --snapshot-dir > active profile > 'default' profile.

    Precedence:
      1. Explicit `--snapshot-dir <path>` flag (any string truthy → that path).
      2. `~/.aa/orgs/<--profile>/snapshots` when a profile is set.
      3. `~/.aa/orgs/default/snapshots` as the final fallback.

    The fallback to a `"default"` profile mirrors the v1.15.0 + Codex-P1
    behavior in `generate`/`batch`: `--git-commit` without `--profile`
    should not error out.
    """
    explicit = getattr(ns, "snapshot_dir", None)
    if explicit:
        return Path(explicit)
    from aa_auto_sdr.core.profiles import default_base

    profile = getattr(ns, "profile", None) or "default"
    return default_base() / "orgs" / profile / "snapshots"
