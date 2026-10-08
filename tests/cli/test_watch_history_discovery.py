"""Watch directory discovery preserves failures before any successful side effects."""

import errno
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aa_auto_sdr.cli.commands.watch import _SnapshotStoreAdapter
from aa_auto_sdr.output.watch_event import StdoutEmitter
from aa_auto_sdr.pipeline.watch import StopToken, WatchContext, run_one_cycle, run_watch_loop
from aa_auto_sdr.snapshot.store import list_snapshots


@pytest.mark.parametrize("failure", [PermissionError("blocked"), OSError(errno.EIO, "I/O error")])
def test_directory_open_failure_propagates_without_loading(tmp_path, monkeypatch, failure):
    (tmp_path / "rs_a").mkdir()
    loader = Mock()
    monkeypatch.setattr(os, "scandir", Mock(side_effect=failure))
    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", loader)
    with pytest.raises(type(failure)) as caught:
        _SnapshotStoreAdapter(tmp_path).latest("rs_a")
    assert caught.value is failure
    loader.assert_not_called()


@pytest.mark.parametrize("state", ["missing_root", "missing_suite", "empty_suite"])
def test_missing_or_empty_history_returns_none(tmp_path, state):
    root = tmp_path / "snapshots"
    if state != "missing_root":
        root.mkdir()
    if state == "empty_suite":
        (root / "rs_a").mkdir()
    assert _SnapshotStoreAdapter(root).latest("rs_a") is None


@pytest.mark.parametrize(
    "failure", [PermissionError("blocked"), OSError(errno.EIO, "I/O error"), FileNotFoundError("gone")]
)
def test_partial_iteration_is_rejected_and_closed(tmp_path, monkeypatch, failure):
    candidate = tmp_path / "rs_a" / "1.json"
    candidate.parent.mkdir()
    candidate.touch()
    loader = Mock(return_value={"rsid": "rs_a", "components": {"report_suite": {}}})
    closed = []

    class InterruptedScan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

        def __iter__(self):
            yield SimpleNamespace(name=candidate.name, path=str(candidate))
            raise failure

    monkeypatch.setattr(os, "scandir", lambda _path: InterruptedScan())
    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", loader)
    with pytest.raises(type(failure)) as caught:
        _SnapshotStoreAdapter(tmp_path).latest("rs_a")
    assert caught.value is failure
    assert closed == [True]
    loader.assert_not_called()


@pytest.mark.parametrize("file_at", ["root", "suite"])
def test_regular_file_directory_is_an_error(tmp_path, file_at):
    root = tmp_path / "snapshots"
    if file_at == "root":
        root.touch()
    else:
        root.mkdir()
        (root / "rs_a").touch()
    with pytest.raises(NotADirectoryError):
        _SnapshotStoreAdapter(root).latest("rs_a")


def test_candidate_membership_and_order_match_shared_listing(tmp_path, monkeypatch):
    rs_dir = tmp_path / "rs_a"
    rs_dir.mkdir()
    for name in ["3.json", "1.json", ".hidden.json", "2.JSON", "4.txt", "5.json.bak"]:
        (rs_dir / name).touch()
    nested = rs_dir / "nested"
    nested.mkdir()
    (nested / "9.json").touch()
    (rs_dir / "6.json").mkdir()
    if os.name != "nt":
        (rs_dir / "7.json").symlink_to(rs_dir / "1.json")
    expected = list_snapshots(tmp_path, rsid="rs_a")
    loaded = []

    def unusable(path):
        loaded.append(path)
        raise json.JSONDecodeError("malformed", "", 0)

    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", unusable)
    assert _SnapshotStoreAdapter(tmp_path).latest("rs_a") is None
    assert loaded == list(reversed(expected))
    assert nested / "9.json" not in loaded
    assert rs_dir / ".hidden.json" in loaded
    assert rs_dir / "6.json" in loaded


def test_matching_directory_reaches_loader_error(tmp_path):
    (tmp_path / "rs_a" / "1.json").mkdir(parents=True)
    with pytest.raises((IsADirectoryError, PermissionError)):
        _SnapshotStoreAdapter(tmp_path).latest("rs_a")


def test_discovered_file_disappearance_is_an_error(tmp_path, monkeypatch):
    candidate = tmp_path / "rs_a" / "1.json"
    candidate.parent.mkdir()
    candidate.touch()
    from aa_auto_sdr.snapshot.store import load_snapshot

    def disappeared(path):
        path.unlink()
        return load_snapshot(path)

    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", disappeared)
    with pytest.raises(FileNotFoundError):
        _SnapshotStoreAdapter(tmp_path).latest("rs_a")


def _document(rsid, day):
    from aa_auto_sdr.api.models import ReportSuite
    from aa_auto_sdr.sdr.document import SdrDocument

    return SdrDocument(
        ReportSuite(rsid=rsid, name="Suite", timezone="UTC", currency="USD", parent_rsid=None),
        [],
        [],
        [],
        [],
        [],
        [],
        datetime(2026, 2, day, tzinfo=UTC),
        "1.0",
    )


@pytest.mark.parametrize("threshold", [0, 1])
def test_denied_discovery_emits_only_error_without_side_effects(tmp_path, monkeypatch, capsys, threshold):
    from aa_auto_sdr.snapshot.store import save_snapshot

    prior = save_snapshot(_document("rs_a", 1), snapshot_dir=tmp_path)
    before = prior.read_bytes()
    store = _SnapshotStoreAdapter(tmp_path)
    save = Mock(wraps=store.save)
    monkeypatch.setattr(store, "save", save)
    monkeypatch.setattr(os, "scandir", Mock(side_effect=PermissionError("blocked")))
    git = Mock()
    monkeypatch.setattr("aa_auto_sdr.pipeline.watch.git_commit_snapshot", git)
    fetcher, publisher = Mock(), Mock()
    ctx = WatchContext(
        fetcher,
        store,
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        StdoutEmitter(),
        git_commit=True,
        git_push=True,
        snapshot_dir=tmp_path,
        notion_publisher=publisher,
    )
    rc, count = run_watch_loop(
        ctx=ctx, rsids=["rs_a"], interval=timedelta(0), threshold=threshold, stop=StopToken(), max_cycles=1
    )
    assert (rc, count) == (0, 1)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["schema"] == "aa-watch-event/v1"
    assert event["event"] == "error"
    assert event["rsid"] == "rs_a"
    assert event["error_type"] == "PermissionError"
    fetcher.fetch_snapshot.assert_not_called()
    save.assert_not_called()
    git.assert_not_called()
    publisher.publish.assert_not_called()
    assert prior.read_bytes() == before


def test_other_suite_continues_and_permission_recovery_compares_original_history(tmp_path, monkeypatch):
    from aa_auto_sdr.snapshot.schema import document_to_envelope
    from aa_auto_sdr.snapshot.store import save_snapshot

    prior = save_snapshot(_document("rs_a", 1), snapshot_dir=tmp_path)
    envelope = document_to_envelope(_document("rs_a", 1))
    envelope["components"]["metrics"] = [{"id": "retired", "name": "Old metric"}]
    prior.write_text(json.dumps(envelope))
    before = prior.read_bytes()
    real_scan = os.scandir
    denied = True
    events, fetched = [], []

    def scan(path):
        nonlocal denied
        if Path(path) == tmp_path / "rs_a" and denied:
            denied = False
            raise PermissionError("blocked")
        return real_scan(path)

    def fetch(rsid):
        fetched.append(rsid)
        return _document(rsid, len(fetched) + 1)

    monkeypatch.setattr(os, "scandir", scan)
    ctx = WatchContext(
        SimpleNamespace(fetch_snapshot=fetch),
        _SnapshotStoreAdapter(tmp_path),
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        SimpleNamespace(emit=events.append),
    )
    rc, count = run_watch_loop(
        ctx=ctx, rsids=["rs_a", "rs_b"], interval=timedelta(0), threshold=1, stop=StopToken(), max_cycles=2
    )
    assert (rc, count) == (0, 2)
    assert fetched == ["rs_b", "rs_a", "rs_b"]
    assert [(e["cycle"], e["rsid"], e["event"]) for e in events] == [
        (0, "rs_a", "error"),
        (0, "rs_b", "baseline"),
        (1, "rs_a", "change"),
    ]
    assert events[-1]["summary"]["removed"] == 1
    assert prior.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory permissions required")
@pytest.mark.parametrize("blocked_at", ["suite", "ancestor"])
def test_real_permission_failure_stops_before_fetch(tmp_path, blocked_at):
    from aa_auto_sdr.snapshot.store import save_snapshot

    root = tmp_path / "snapshots"
    prior = save_snapshot(_document("rs_a", 1), snapshot_dir=root)
    before = prior.read_bytes()
    blocked = prior.parent if blocked_at == "suite" else root
    mode = blocked.stat().st_mode
    blocked.chmod(0o300 if blocked_at == "suite" else 0o000)
    fetcher = Mock()
    try:
        try:
            with os.scandir(prior.parent) as entries:
                list(entries)
        except PermissionError:
            pass
        else:
            pytest.skip("environment does not enforce directory permissions")
        result = run_one_cycle(
            rsid="rs_a",
            ctx=WatchContext(
                fetcher, _SnapshotStoreAdapter(root), Mock(utcnow=lambda: datetime.now(UTC)), Mock(), Mock()
            ),
        )
        assert result.kind == "fetch_error"
        assert isinstance(result.error, PermissionError)
        fetcher.fetch_snapshot.assert_not_called()
    finally:
        blocked.chmod(mode)
    assert prior.read_bytes() == before
