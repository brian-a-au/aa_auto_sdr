"""snapshot/git.py — `git show <ref>:<path>` wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import SnapshotResolveError
from aa_auto_sdr.snapshot.git import git_show


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed file (history of two versions)."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
    snap = tmp_path / "snapshots" / "demo.prod" / "2026-04-26T10-00-00+00-00.json"
    snap.parent.mkdir(parents=True)
    snap.write_text('{"schema": "aa-sdr-snapshot/v1", "marker": "v1"}\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v1"], cwd=tmp_path, check=True)
    snap.write_text('{"schema": "aa-sdr-snapshot/v1", "marker": "v2"}\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=tmp_path, check=True)
    return tmp_path


def test_git_show_reads_file_at_head(tiny_repo: Path) -> None:
    out = git_show(
        ref="HEAD",
        path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
        repo_root=tiny_repo,
    )
    assert "v2" in out


def test_git_show_reads_file_at_head_minus_one(tiny_repo: Path) -> None:
    out = git_show(
        ref="HEAD~1",
        path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
        repo_root=tiny_repo,
    )
    assert "v1" in out
    assert "v2" not in out


def test_git_show_raises_on_unknown_ref(tiny_repo: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="git show"):
        git_show(
            ref="nonexistent-branch",
            path="snapshots/demo.prod/2026-04-26T10-00-00+00-00.json",
            repo_root=tiny_repo,
        )


def test_git_show_raises_on_unknown_path(tiny_repo: Path) -> None:
    with pytest.raises(SnapshotResolveError, match="git show"):
        git_show(ref="HEAD", path="nope.json", repo_root=tiny_repo)


def test_git_show_raises_outside_repo(tmp_path: Path) -> None:
    """Run against a directory that isn't a git repo."""
    with pytest.raises(SnapshotResolveError):
        git_show(ref="HEAD", path="anything.json", repo_root=tmp_path)


@pytest.mark.parametrize(
    ("ref", "path"),
    [
        ("--output=/tmp/pwned", "x.json"),
        ("-p", "x.json"),
        ("HEAD", "-x.json"),
        ("HEAD", "--help"),
    ],
)
def test_git_show_rejects_option_like_ref_or_path(ref: str, path: str, tmp_path: Path, monkeypatch) -> None:
    def _no_subprocess(*args, **kwargs):
        raise AssertionError("git must not be invoked for an option-like ref or path")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    with pytest.raises(SnapshotResolveError, match="must not start with '-'"):
        git_show(ref=ref, path=path, repo_root=tmp_path)


def _commit_bytes(repo: Path, name: str, data: bytes) -> None:
    (repo / name).write_bytes(data)
    subprocess.run(["git", "add", name], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", name], cwd=repo, check=True)


def test_git_show_non_utf8_blob_raises_resolve_error(tiny_repo: Path) -> None:
    # A Latin-1 byte (0xE9) is not UTF-8; it must surface as a snapshot
    # error (exit 16), the same as the filesystem path reader.
    _commit_bytes(tiny_repo, "latin1.json", b'{"name": "Caf\xe9"}\n')
    with pytest.raises(SnapshotResolveError, match="not valid UTF-8"):
        git_show(ref="HEAD", path="latin1.json", repo_root=tiny_repo)


def test_git_show_decodes_utf8_regardless_of_locale(tiny_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # text=True decodes with the locale encoding (cp1252 on Windows), which
    # turns UTF-8 names into mojibake and reports false name changes.
    import locale

    monkeypatch.setattr(locale, "getpreferredencoding", lambda *_args: "latin-1")
    monkeypatch.setattr(locale, "getencoding", lambda: "latin-1")
    _commit_bytes(tiny_repo, "utf8.json", '{"name": "Café — 日本"}\n'.encode())
    assert git_show(ref="HEAD", path="utf8.json", repo_root=tiny_repo) == '{"name": "Café — 日本"}\n'


def test_git_show_crlf_blob_still_parses(tiny_repo: Path) -> None:
    import json

    _commit_bytes(tiny_repo, "crlf.json", b'{\r\n  "marker": "crlf"\r\n}\r\n')
    assert json.loads(git_show(ref="HEAD", path="crlf.json", repo_root=tiny_repo)) == {"marker": "crlf"}
