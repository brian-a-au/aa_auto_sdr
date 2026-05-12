"""Shared helpers for CLI command modules.

Currently exposes `resolve_snapshot_dir`, used by `generate`, `batch`, and
`watch` to settle the snapshot directory from `--snapshot-dir` / `--profile`.
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

    The fallback to a `"default"` profile means `--git-commit` without
    `--profile` resolves to a valid snapshot dir instead of erroring out.
    """
    explicit = getattr(ns, "snapshot_dir", None)
    if explicit:
        return Path(explicit)
    from aa_auto_sdr.core.profiles import default_base

    profile = getattr(ns, "profile", None) or "default"
    return default_base() / "orgs" / profile / "snapshots"
