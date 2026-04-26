"""Snapshot resolver.

Token grammar (see v0.7 spec §4):

  <path>                             filesystem path to a JSON snapshot
  <rsid>@<timestamp-with-hyphens>    profile-scoped, exact match
  <rsid>@latest                      most-recent in profile dir
  <rsid>@previous                    second-most-recent in profile dir
  git:<ref>:<path-in-repo>           subprocess `git show`

Returns the validated envelope dict; the caller passes it to
snapshot.comparator.compare()."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.core.json_io import read_json
from aa_auto_sdr.snapshot.git import git_show
from aa_auto_sdr.snapshot.schema import validate_envelope


def resolve_snapshot(
    token: str,
    *,
    profile_snapshot_dir: Path | None,
    repo_root: Path | None,
) -> dict[str, Any]:
    """Resolve `token` to a validated snapshot envelope dict."""
    if token.startswith("git:"):
        return _resolve_git(token, repo_root=repo_root)
    if "@" in token and not _looks_like_path(token):
        return _resolve_rsid_at(token, profile_snapshot_dir=profile_snapshot_dir)
    path = Path(token).expanduser()
    if path.exists():
        return _resolve_path(path)
    # Token doesn't match any known form. Use the spec §4 message when the token
    # has no path-shape signals; otherwise surface the path-not-found error.
    if not _looks_like_path(token):
        raise SnapshotResolveError(
            f"could not interpret '{token}' as snapshot path, <rsid>@<spec>, or git:<ref>:<path>",
        )
    raise SnapshotResolveError(f"snapshot file not found: {path}")


def _looks_like_path(token: str) -> bool:
    """Heuristic: tokens with a path separator or that point to an existing file are paths."""
    if os.sep in token or token.startswith(("./", "~")):
        return True
    return Path(token).exists()


def _resolve_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SnapshotResolveError(f"snapshot file not found: {path}")
    if path.is_dir():
        raise SnapshotResolveError(f"expected snapshot file but got directory: {path}")
    try:
        env = read_json(path)
    except json.JSONDecodeError as exc:
        raise SnapshotResolveError(f"snapshot file {path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise SnapshotResolveError(f"could not read snapshot file {path}: {exc}") from exc
    validate_envelope(env)
    return env


def _resolve_rsid_at(token: str, *, profile_snapshot_dir: Path | None) -> dict[str, Any]:
    if profile_snapshot_dir is None:
        raise SnapshotResolveError(f"'{token}' requires --profile (snapshots are profile-scoped)")
    rsid, _, spec = token.rpartition("@")
    if not rsid or not spec:
        raise SnapshotResolveError(f"could not parse '{token}' as <rsid>@<spec>")
    rs_dir = profile_snapshot_dir / rsid
    if not rs_dir.exists():
        raise SnapshotResolveError(f"no snapshots for {rsid} in profile dir {profile_snapshot_dir}")
    files = sorted(rs_dir.glob("*.json"))
    if not files:
        raise SnapshotResolveError(f"no snapshots for {rsid} in {rs_dir}")
    if spec == "latest":
        return _resolve_path(files[-1])
    if spec == "previous":
        if len(files) < 2:
            raise SnapshotResolveError(f"only one snapshot for {rsid}; @previous needs at least two")
        return _resolve_path(files[-2])
    # exact timestamp
    target = rs_dir / f"{spec}.json"
    if not target.exists():
        raise SnapshotResolveError(f"snapshot {token} not found at {target}")
    return _resolve_path(target)


def _resolve_git(token: str, *, repo_root: Path | None) -> dict[str, Any]:
    # token format: git:<ref>:<path>
    body = token[len("git:") :]
    ref, sep, path = body.partition(":")
    if not sep or not ref or not path:
        raise SnapshotResolveError(f"could not parse '{token}' as git:<ref>:<path>")
    root = repo_root if repo_root is not None else Path.cwd()
    raw = git_show(ref=ref, path=path, repo_root=root)
    try:
        env = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SnapshotResolveError(f"{token} did not decode as JSON: {exc}") from exc
    validate_envelope(env)
    return env
