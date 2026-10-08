"""Offline watch recovery through real snapshot files and the real adapter."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aa_auto_sdr.cli.commands.watch import _SnapshotStoreAdapter
from aa_auto_sdr.pipeline.watch import StopToken, WatchContext, run_one_cycle, run_watch_loop


def envelope(rsid="rs_a", *, metrics=None):
    return {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": rsid,
        "captured_at": "2026-01-01T00:00:00Z",
        "tool_version": "1.0",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "components": {"report_suite": {"rsid": rsid}, "metrics": metrics or []},
    }


def history(tmp_path, payload, name="2099-01-01T00-00-00Z.json", rsid="rs_a"):
    path = tmp_path / rsid / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
    return path


def test_truncated_latest_recovers_older_preserving_bytes(tmp_path, caplog):
    older = history(tmp_path, envelope(), "2026-01-01T00-00-00Z.json")
    broken = history(tmp_path, b'{"secret_payload":')
    assert _SnapshotStoreAdapter(tmp_path).latest("rs_a")["rsid"] == "rs_a"
    assert broken.read_bytes() == b'{"secret_payload":'
    assert older.exists()
    warning = next(r for r in caplog.records if r.levelname == "WARNING")
    assert warning.rsid == "rs_a"
    assert warning.error_class == "JSONDecodeError"
    assert str(broken) in warning.message
    assert "secret_payload" not in warning.message


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        {},
        {
            "schema": "aa-sdr-snapshot/v4",
            "rsid": "rs_a",
            "captured_at": "2026-01-01T00:00:00Z",
            "tool_version": "1",
            "components": {},
        },
        envelope(metrics=[{}]),
        envelope(metrics=[{"id": []}]),
        envelope(metrics=[{"id": "a"}, {"id": 1}]),
    ],
)
def test_all_unusable_candidates_establish_no_history(tmp_path, payload):
    path = history(tmp_path, payload)
    before = path.read_bytes()
    assert _SnapshotStoreAdapter(tmp_path).latest("rs_a") is None
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", [PermissionError("blocked"), RuntimeError("unexpected")])
def test_read_failures_stop_before_fetch(tmp_path, monkeypatch, failure):
    history(tmp_path, envelope())
    monkeypatch.setattr("aa_auto_sdr.snapshot.store.load_snapshot", Mock(side_effect=failure))
    fetcher = Mock()
    result = run_one_cycle(
        rsid="rs_a",
        ctx=WatchContext(
            fetcher, _SnapshotStoreAdapter(tmp_path), Mock(utcnow=lambda: datetime.now(UTC)), Mock(), Mock()
        ),
    )
    assert result.error is failure
    fetcher.fetch_snapshot.assert_not_called()


@pytest.mark.parametrize("payload", [dict(envelope(), schema="aa-sdr-snapshot/v5"), envelope("wrong")])
def test_nonrecoverable_history_blocks_fetch(tmp_path, payload):
    history(tmp_path, payload)
    fetcher = Mock()
    result = run_one_cycle(
        rsid="rs_a",
        ctx=WatchContext(
            fetcher, _SnapshotStoreAdapter(tmp_path), Mock(utcnow=lambda: datetime.now(UTC)), Mock(), Mock()
        ),
    )
    assert result.kind == "fetch_error"
    assert type(result.error).__name__ == "SnapshotSchemaError"
    fetcher.fetch_snapshot.assert_not_called()


def document(rsid, cycle):
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
        datetime(2026, 2, cycle, tzinfo=UTC),
        "1.0",
    )


@pytest.mark.parametrize(
    ("threshold", "events", "publications"), [(1, ["baseline"], 1), (0, ["baseline", "change"], 1)]
)
def test_all_corrupt_then_real_saved_baseline_compares_next_cycle(tmp_path, threshold, events, publications):
    broken = history(tmp_path, b"{")
    fetched = []
    emitted = []
    publisher = Mock()
    clock = Mock(utcnow=lambda: datetime(2026, 2, 1, tzinfo=UTC))

    def fetch(rsid):
        fetched.append(rsid)
        return document(rsid, len(fetched))

    ctx = WatchContext(
        SimpleNamespace(fetch_snapshot=fetch),
        _SnapshotStoreAdapter(tmp_path),
        clock,
        Mock(),
        SimpleNamespace(emit=emitted.append),
        notion_publisher=publisher,
    )
    rc, count = run_watch_loop(
        ctx=ctx, rsids=["rs_a"], interval=timedelta(0), threshold=threshold, stop=StopToken(), max_cycles=2
    )
    assert rc == 0
    assert count == 2
    assert fetched == ["rs_a", "rs_a"]
    assert [event["event"] for event in emitted] == events
    assert publisher.publish.call_count == publications
    assert broken.read_bytes() == b"{"
    if threshold == 0:
        assert (
            emitted[-1]["summary"]["added"]
            == emitted[-1]["summary"]["removed"]
            == emitted[-1]["summary"]["modified"]
            == 0
        )


def test_unsupported_suite_does_not_block_other_suite_or_later_cycles(tmp_path):
    history(tmp_path, dict(envelope(), schema="aa-sdr-snapshot/v5"))
    calls = []
    events = []

    def fetch(rsid):
        calls.append(rsid)
        return document(rsid, len(calls))

    ctx = WatchContext(
        SimpleNamespace(fetch_snapshot=fetch),
        _SnapshotStoreAdapter(tmp_path),
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        SimpleNamespace(emit=events.append),
    )
    run_watch_loop(ctx=ctx, rsids=["rs_a", "rs_b"], interval=timedelta(0), threshold=1, stop=StopToken(), max_cycles=2)
    assert calls == ["rs_b", "rs_b"]
    assert [(e["rsid"], e["event"]) for e in events] == [("rs_a", "error"), ("rs_b", "baseline"), ("rs_a", "error")]


@pytest.mark.parametrize("stage", ["fetch", "save"])
def test_recovered_history_fetch_or_save_failure_preserves_prior_files(tmp_path, monkeypatch, stage):
    older = history(tmp_path, envelope(), "2026-01-01T00-00-00Z.json")
    broken = history(tmp_path, b"{")
    originals = {p: p.read_bytes() for p in [older, broken]}
    fetcher = Mock(fetch_snapshot=Mock(return_value=document("rs_a", 1)))
    if stage == "fetch":
        fetcher.fetch_snapshot.side_effect = RuntimeError("fetch failed")
    else:
        monkeypatch.setattr("aa_auto_sdr.snapshot.store.save_snapshot", Mock(side_effect=OSError("disk full")))
    ctx = WatchContext(
        fetcher,
        _SnapshotStoreAdapter(tmp_path),
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        Mock(),
        notion_publisher=Mock(),
    )
    result = run_one_cycle(rsid="rs_a", ctx=ctx)
    assert result.kind == "fetch_error"
    assert result.snapshot_path is None
    assert {p: p.read_bytes() for p in originals} == originals


def test_corrupt_newest_does_not_skip_unsupported_next_candidate(tmp_path):
    history(tmp_path, envelope(), "2026-01-01T00-00-00Z.json")
    history(tmp_path, dict(envelope(), schema="foreign/v1"), "2027-01-01T00-00-00Z.json")
    history(tmp_path, b"{")
    from aa_auto_sdr.core.exceptions import SnapshotSchemaError

    with pytest.raises(SnapshotSchemaError):
        _SnapshotStoreAdapter(tmp_path).latest("rs_a")


@pytest.mark.parametrize(("threshold", "expected_events", "expected_git"), [(1, [], 0), (0, ["change"], 1)])
def test_recovery_ignored_fields_preserves_git_and_notion_gates(
    tmp_path, monkeypatch, threshold, expected_events, expected_git
):
    from dataclasses import replace

    from aa_auto_sdr.snapshot.git import GitOpResult
    from aa_auto_sdr.snapshot.store import save_snapshot

    old = document("rs_a", 1)
    current = document("rs_a", 2)
    current = replace(current, report_suite=replace(current.report_suite, name="Changed name"))
    save_snapshot(old, snapshot_dir=tmp_path)
    history(tmp_path, b"{")
    events = []
    publish = Mock()
    commit = Mock(return_value=GitOpResult(ok=True, committed=False, commit_sha=None, pushed=False))
    monkeypatch.setattr("aa_auto_sdr.pipeline.watch.git_commit_snapshot", commit)
    ctx = WatchContext(
        SimpleNamespace(fetch_snapshot=lambda _rsid: current),
        _SnapshotStoreAdapter(tmp_path),
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        SimpleNamespace(emit=events.append),
        ignore_fields=frozenset({"name"}),
        git_commit=True,
        snapshot_dir=tmp_path,
        notion_publisher=publish,
    )
    run_watch_loop(ctx=ctx, rsids=["rs_a"], interval=timedelta(0), threshold=threshold, stop=StopToken(), max_cycles=1)
    assert [e["event"] for e in events] == expected_events
    assert commit.call_count == expected_git
    publish.publish.assert_not_called()


@pytest.mark.parametrize("suppressed", [False, True])
def test_recovery_change_counts_and_publication_use_comparable_sections(tmp_path, monkeypatch, suppressed):
    from aa_auto_sdr.snapshot.git import GitOpResult
    from aa_auto_sdr.snapshot.schema import document_to_envelope

    prior = document_to_envelope(document("rs_a", 1))
    prior["components"]["classifications"] = [{"id": "retired", "name": "Old dataset"}]
    if suppressed:
        prior["degraded_components"] = ["classifications"]
    history(tmp_path, prior, "2026-02-01T00-00-00Z.json")
    broken = history(tmp_path, b"{")
    second_broken = history(tmp_path, b"\xff", "2098-01-01T00-00-00Z.json")
    events = []
    publisher = Mock()
    commit = Mock(return_value=GitOpResult(ok=True, committed=True, commit_sha="abc", pushed=False))
    monkeypatch.setattr("aa_auto_sdr.pipeline.watch.git_commit_snapshot", commit)
    ctx = WatchContext(
        SimpleNamespace(fetch_snapshot=lambda rsid: document(rsid, 2)),
        _SnapshotStoreAdapter(tmp_path),
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        SimpleNamespace(emit=events.append),
        git_commit=True,
        snapshot_dir=tmp_path,
        notion_publisher=publisher,
    )
    run_watch_loop(ctx=ctx, rsids=["rs_a"], interval=timedelta(0), threshold=1, stop=StopToken(), max_cycles=1)
    assert second_broken.read_bytes() == b"\xff"
    assert commit.call_count == publisher.publish.call_count == (0 if suppressed else 1)
    if suppressed:
        assert events == []
    else:
        assert events[0]["event"] == "change"
        assert events[0]["summary"]["removed"] == 1
        assert events[0]["git"]["commit_sha"] == "abc"
    assert broken.read_bytes() == b"{"


def test_shared_minimal_envelope_loads_but_watch_requires_report_suite(tmp_path):
    from aa_auto_sdr.snapshot.store import load_snapshot

    minimal = envelope()
    minimal["components"] = {}
    path = history(tmp_path, minimal)
    assert load_snapshot(path)["components"] == {}
    assert _SnapshotStoreAdapter(tmp_path).latest("rs_a") is None


def test_recovered_diff_spans_older_capture_to_fresh_capture(tmp_path):
    from aa_auto_sdr.snapshot.schema import document_to_envelope

    older = document_to_envelope(document("rs_a", 1))
    older["components"]["metrics"] = [{"id": "retired", "name": "Old metric"}]
    history(tmp_path, older, "2026-02-01T00-00-00Z.json")
    first = history(tmp_path, b"{", "2098-01-01T00-00-00Z.json")
    second = history(tmp_path, b"\xff")
    ctx = WatchContext(
        SimpleNamespace(fetch_snapshot=lambda rsid: document(rsid, 2)),
        _SnapshotStoreAdapter(tmp_path),
        Mock(utcnow=lambda: datetime.now(UTC)),
        Mock(),
        Mock(),
    )
    result = run_one_cycle(rsid="rs_a", ctx=ctx)
    assert result.kind == "diffed"
    assert result.diff.a_captured_at == older["captured_at"]
    assert result.diff.b_captured_at == "2026-02-02T00:00:00+00:00"
    assert result.diff.components[1].removed[0].id == "retired"
    assert first.read_bytes() == b"{"
    assert second.read_bytes() == b"\xff"
