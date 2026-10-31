#!/usr/bin/env python3
"""Delete GitHub Actions caches that no workflow run can restore again.

A cache saved by a pull request is readable only by that pull request, so once
it closes those entries are dead weight. setup-uv keys embed a hash of
uv.lock, so on main only the newest entry of each key family can still be hit;
every older generation is unreachable after the next lockfile change. Dead
entries count toward the 10 GB repository limit, and past it GitHub evicts the
least recently used entries, which can include the ones main still needs.

Dry run by default; --apply deletes. Uses only the standard library and `gh`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from typing import Any

REPOSITORY = "brian-a-au/aa_auto_sdr"
DEFAULT_BRANCH_REF = "refs/heads/main"
# The uv.lock hash setup-uv puts in its key: hex, 64 characters for sha256.
_LOCK_HASH = re.compile(r"-[0-9a-f]{40,}(?=-|$)")
_PULL_REF = re.compile(r"refs/pull/(\d+)/merge")
_BRANCH_REF = re.compile(r"refs/heads/(.+)")


def key_family(key: str) -> str | None:
    """Return the setup-uv key with its lockfile hash removed, or None."""
    if not key.startswith("setup-uv-"):
        return None
    family, count = _LOCK_HASH.subn("-<lock>", key)
    return family if count == 1 else None


def plan_deletions(
    caches: Iterable[dict[str, Any]],
    pr_is_open: Callable[[int], bool],
    branch_exists: Callable[[str], bool],
) -> list[tuple[dict[str, Any], str]]:
    """Choose the caches to delete, each with the reason."""
    doomed: list[tuple[dict[str, Any], str]] = []
    newest: dict[str, dict[str, Any]] = {}
    for cache in caches:
        ref = cache["ref"]
        if ref == DEFAULT_BRANCH_REF:
            family = key_family(cache["key"])
            if family is None:
                continue  # Not ours (CodeQL and others manage their own).
            kept = newest.get(family)
            if kept is None:
                newest[family] = cache
            elif cache["created_at"] > kept["created_at"]:
                newest[family] = cache
                doomed.append((kept, "superseded on main"))
            else:
                doomed.append((cache, "superseded on main"))
        elif (pull := _PULL_REF.fullmatch(ref)) is not None:
            if not pr_is_open(int(pull.group(1))):
                doomed.append((cache, "pull request closed"))
        elif (branch := _BRANCH_REF.fullmatch(ref)) is not None:
            if not branch_exists(branch.group(1)):
                doomed.append((cache, "branch deleted"))
    return doomed


def _gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=False, timeout=60)


def list_caches(repo: str) -> list[dict[str, Any]]:
    result = _gh("api", "--paginate", f"repos/{repo}/actions/caches?per_page=100", "--jq", ".actions_caches[]")
    if result.returncode != 0:
        raise RuntimeError(f"listing caches failed: {result.stderr.strip()}")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=REPOSITORY)
    parser.add_argument("--apply", action="store_true", help="delete the caches (default: dry run)")
    args = parser.parse_args(argv)

    pr_state: dict[int, bool] = {}

    def pr_is_open(number: int) -> bool:
        if number not in pr_state:
            result = _gh("api", f"repos/{args.repo}/pulls/{number}", "--jq", ".state")
            if result.returncode != 0:
                raise RuntimeError(f"reading PR #{number} failed: {result.stderr.strip()}")
            pr_state[number] = result.stdout.strip() == "open"
        return pr_state[number]

    def branch_exists(name: str) -> bool:
        result = _gh("api", f"repos/{args.repo}/branches/{name}", "--silent")
        if result.returncode == 0:
            return True
        if "404" in result.stderr:
            return False
        raise RuntimeError(f"reading branch {name} failed: {result.stderr.strip()}")

    caches = list_caches(args.repo)
    doomed = plan_deletions(caches, pr_is_open, branch_exists)
    total = sum(cache["size_in_bytes"] for cache in caches)
    freed = sum(cache["size_in_bytes"] for cache, _ in doomed)
    for cache, reason in doomed:
        print(f"{'delete' if args.apply else 'would delete'}: {cache['ref']} {cache['key']} ({reason})")
        if args.apply:
            result = _gh("api", "-X", "DELETE", f"repos/{args.repo}/actions/caches/{cache['id']}", "--silent")
            # Another run may have deleted or evicted it already.
            if result.returncode != 0 and "404" not in result.stderr:
                raise RuntimeError(f"deleting cache {cache['id']} failed: {result.stderr.strip()}")
    verb = "Freed" if args.apply else "Would free"
    print(
        f"{verb} {freed / 1e9:.2f} GB in {len(doomed)} of {len(caches)} caches; {(total - freed) / 1e9:.2f} GB remains."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
