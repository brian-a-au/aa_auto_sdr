from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest

from aa_auto_sdr.core.atomic_io import atomic_write_path, atomic_write_text


def _staging_files(directory: Path) -> list[Path]:
    return [path for path in directory.iterdir() if path.name.startswith(".")]


def test_atomic_write_text_replaces_absent_destination(tmp_path: Path) -> None:
    target = tmp_path / "report.md"

    atomic_write_text(target, "complete\n", encoding="utf-8")

    assert target.read_bytes() == b"complete\n"
    assert _staging_files(tmp_path) == []


@pytest.mark.parametrize("destination_exists", [False, True])
def test_atomic_write_path_cleans_partial_stage_on_callback_failure(
    tmp_path: Path,
    destination_exists: bool,
) -> None:
    target = tmp_path / "report.html"
    if destination_exists:
        target.write_bytes(b"original")
    failure = RuntimeError("serializer failed")

    def fail_after_partial_write(staged: Path) -> None:
        staged.write_bytes(b"partial")
        raise failure

    with pytest.raises(RuntimeError) as exc_info:
        atomic_write_path(target, fail_after_partial_write)

    assert exc_info.value is failure
    if destination_exists:
        assert target.read_bytes() == b"original"
    else:
        assert not target.exists()
    assert _staging_files(tmp_path) == []


@pytest.mark.parametrize("destination_exists", [False, True])
def test_atomic_write_path_cleans_completed_stage_on_replace_failure(
    tmp_path: Path,
    destination_exists: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "report.json"
    if destination_exists:
        target.write_bytes(b"original")
    failure = PermissionError("destination locked")

    def fail_replace(source: Path, destination: Path) -> None:
        raise failure

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)

    with pytest.raises(PermissionError) as exc_info:
        atomic_write_path(target, lambda staged: staged.write_bytes(b"complete"))

    assert exc_info.value is failure
    if destination_exists:
        assert target.read_bytes() == b"original"
    else:
        assert not target.exists()
    assert _staging_files(tmp_path) == []


def test_atomic_write_path_cleans_up_for_base_exception(tmp_path: Path) -> None:
    target = tmp_path / "report.txt"

    class AbortWrite(BaseException):
        pass

    def abort(staged: Path) -> None:
        staged.write_text("partial")
        raise AbortWrite

    with pytest.raises(AbortWrite):
        atomic_write_path(target, abort)

    assert not target.exists()
    assert _staging_files(tmp_path) == []


def test_atomic_write_path_uses_closed_sibling_with_destination_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "report.xlsx"
    closed_fds: list[int] = []
    real_close = os.close

    def record_close(fd: int) -> None:
        real_close(fd)
        closed_fds.append(fd)

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.close", record_close)

    def serialize(staged: Path) -> None:
        assert staged.parent == target.parent
        assert staged.suffix == ".xlsx"
        assert closed_fds
        staged.write_bytes(b"workbook")

    atomic_write_path(target, serialize)

    assert target.read_bytes() == b"workbook"
    assert _staging_files(tmp_path) == []


def test_atomic_write_path_uses_distinct_stages_for_concurrent_writes(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    barrier = Barrier(2)
    paths: list[Path] = []
    paths_lock = Lock()

    def write(content: bytes) -> None:
        def serialize(staged: Path) -> None:
            staged.write_bytes(content)
            with paths_lock:
                paths.append(staged)
            barrier.wait()

        atomic_write_path(target, serialize)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write, content) for content in (b"first", b"second")]
        for future in futures:
            future.result()

    assert len(set(paths)) == 2
    assert target.read_bytes() in {b"first", b"second"}
    assert _staging_files(tmp_path) == []


def test_atomic_write_path_does_not_create_missing_parent(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "report.txt"

    with pytest.raises(FileNotFoundError):
        atomic_write_text(target, "content")

    assert not target.parent.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable to Windows")
def test_atomic_write_path_preserves_existing_destination_mode(tmp_path: Path) -> None:
    target = tmp_path / "shared.txt"
    target.write_text("original")
    target.chmod(0o640)

    atomic_write_text(target, "replacement")

    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable to Windows")
def test_atomic_write_path_new_destination_matches_direct_creation_mode(tmp_path: Path) -> None:
    direct = tmp_path / "direct.txt"
    target = tmp_path / "atomic.txt"
    direct.write_text("direct")

    atomic_write_text(target, "atomic")

    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(direct.stat().st_mode)
