"""scripts/prune_actions_cache.py: which caches are dead, and dry run vs apply."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "prune_actions_cache", Path(__file__).parent.parent / "scripts" / "prune_actions_cache.py"
)
assert _spec is not None
assert _spec.loader is not None
prune = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prune)

OLD = "a" * 64
NEW = "b" * 64


def cache(key: str, ref: str = "refs/heads/main", created: str = "2026-10-31T00:00:00Z", **extra) -> dict:
    return {
        "id": hash((key, ref, created)) & 0xFFFF,
        "key": key,
        "ref": ref,
        "created_at": created,
        "size_in_bytes": 1_000_000,
        **extra,
    }


def uv_key(python: str, lock: str, suffix: str = "") -> str:
    return f"setup-uv-2-x86_64-unknown-linux-gnu-ubuntu-24.04-{python}-{lock}{suffix}"


def never(_):
    raise AssertionError("lookup not expected")


@pytest.mark.parametrize(
    ("key", "family"),
    [
        (uv_key("3.14", NEW), "setup-uv-2-x86_64-unknown-linux-gnu-ubuntu-24.04-3.14-<lock>"),
        (
            uv_key("3.15", NEW, "-lowest-direct"),
            "setup-uv-2-x86_64-unknown-linux-gnu-ubuntu-24.04-3.15-<lock>-lowest-direct",
        ),
        ("codeql-overlay-base-database-1-d953d79b74456ce0-python-2.27.3", None),
        ("setup-uv-2-x86_64-unknown-linux-gnu-ubuntu-24.04-3.14", None),
    ],
)
def test_key_family(key, family):
    assert prune.key_family(key) == family


def test_main_keeps_only_the_newest_generation_of_each_family():
    stale = cache(uv_key("3.14", OLD), created="2026-10-01T00:00:00Z")
    current = cache(uv_key("3.14", NEW), created="2026-10-30T00:00:00Z")
    other_python = cache(uv_key("3.11", OLD), created="2026-10-01T00:00:00Z")
    lowest = cache(uv_key("3.14", OLD, "-lowest-direct"), created="2026-10-01T00:00:00Z")
    codeql = cache("codeql-overlay-base-database-1-d953d79b74456ce0-python-2.27.3-41157895552-1")
    # Order must not matter: the newest wins whether it comes first or last.
    for caches in ([stale, current, other_python, lowest, codeql], [current, codeql, lowest, other_python, stale]):
        assert prune.plan_deletions(caches, never, never) == [(stale, "superseded on main")]


def test_closed_pull_requests_and_deleted_branches_lose_their_caches():
    closed = cache(uv_key("3.14", NEW), ref="refs/pull/7/merge")
    still_open = cache(uv_key("3.14", NEW), ref="refs/pull/8/merge")
    gone = cache(uv_key("3.14", NEW), ref="refs/heads/dependabot/uv/ruff-0.17.3")
    live = cache(uv_key("3.14", NEW), ref="refs/heads/feature")
    doomed = prune.plan_deletions(
        [closed, still_open, gone, live],
        pr_is_open=lambda number: number == 8,
        branch_exists=lambda name: name == "feature",
    )
    assert doomed == [(closed, "pull request closed"), (gone, "branch deleted")]


class FakeGh:
    """Stands in for `gh api`, recording every call."""

    def __init__(self, caches: list[dict], delete_stderr: str = "") -> None:
        self.caches = caches
        self.delete_stderr = delete_stderr
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if "--paginate" in args:
            stdout = "\n".join(json.dumps(c) for c in self.caches)
            return subprocess.CompletedProcess(args, 0, stdout, "")
        if "-X" in args:
            code = 1 if self.delete_stderr else 0
            return subprocess.CompletedProcess(args, code, "", self.delete_stderr)
        if "/pulls/" in args[1]:
            return subprocess.CompletedProcess(args, 0, "closed\n", "")
        raise AssertionError(f"unexpected gh call: {args}")

    @property
    def deletes(self) -> list[str]:
        return [args[-2] for args in self.calls if "-X" in args]


@pytest.fixture
def fake(monkeypatch) -> FakeGh:
    gh = FakeGh([cache(uv_key("3.14", NEW), ref="refs/pull/7/merge", id=11)])
    monkeypatch.setattr(prune, "_gh", gh)
    return gh


def test_dry_run_deletes_nothing(fake, capsys):
    assert prune.main([]) == 0
    assert fake.deletes == []
    out = capsys.readouterr().out
    assert "would delete: refs/pull/7/merge" in out
    assert "Would free 0.00 GB in 1 of 1 caches" in out


def test_apply_deletes_and_tolerates_already_gone(fake, capsys):
    assert prune.main(["--apply"]) == 0
    assert fake.deletes == ["repos/brian-a-au/aa_auto_sdr/actions/caches/11"]
    fake.delete_stderr = "gh: Not Found (HTTP 404)"
    assert prune.main(["--apply"]) == 0
    assert "Freed" in capsys.readouterr().out


def test_apply_fails_on_other_delete_errors(fake):
    fake.delete_stderr = "gh: Resource not accessible by integration (HTTP 403)"
    with pytest.raises(RuntimeError, match="deleting cache 11 failed"):
        prune.main(["--apply"])
