"""Pipeline composition with git ops (single / batch / watch)."""

from __future__ import annotations

import argparse  # noqa: F401
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest  # noqa: F401

from aa_auto_sdr.snapshot.git import GitOpResult


class TestSingleModeGit:
    def test_run_single_returns_git_op_when_git_commit_true(self, tmp_path: Path) -> None:
        from aa_auto_sdr.pipeline import single as single_mod

        fake_doc = _fake_sdr_doc(rsid="rs_a")
        fake_path = tmp_path / "rs_a" / "snap.json"
        fake_path.parent.mkdir(parents=True)
        fake_path.write_text("{}")

        fake_writer = MagicMock()
        fake_writer.extension = ".json"
        fake_writer.write.return_value = [tmp_path / "out" / "rs_a.json"]

        with (
            patch.object(single_mod, "build_sdr", return_value=fake_doc),
            patch.object(single_mod.registry, "get_writer", return_value=fake_writer),
            patch.object(single_mod.registry, "bootstrap"),
            patch("aa_auto_sdr.snapshot.store.save_snapshot", return_value=fake_path),
            patch(
                "aa_auto_sdr.snapshot.git.git_commit_snapshot",
                return_value=GitOpResult(
                    ok=True,
                    committed=True,
                    pushed=False,
                    commit_sha="abc1234567abc1234567abc1234567abc1234567",
                ),
            ) as mock_commit,
        ):
            result = single_mod.run_single(
                client=_fake_client(),
                rsid="rs_a",
                formats=["json"],
                output_dir=tmp_path / "out",
                captured_at=_now_utc(),
                tool_version="1.15.0",
                snapshot_dir=tmp_path,
                git_commit=True,
                git_push=False,
                git_message=None,
            )

        assert result.success is True
        assert result.git_op is not None
        assert result.git_op.ok is True
        assert result.git_op.committed is True
        assert result.git_op.commit_sha is not None
        assert len(result.git_op.commit_sha) == 40
        mock_commit.assert_called_once()

    def test_run_single_no_git_op_when_git_commit_false(self, tmp_path: Path) -> None:
        from aa_auto_sdr.pipeline import single as single_mod

        fake_writer2 = MagicMock()
        fake_writer2.extension = ".json"
        fake_writer2.write.return_value = [tmp_path / "out" / "rs_a.json"]

        with (
            patch.object(single_mod, "build_sdr", return_value=_fake_sdr_doc(rsid="rs_a")),
            patch.object(single_mod.registry, "get_writer", return_value=fake_writer2),
            patch.object(single_mod.registry, "bootstrap"),
            patch("aa_auto_sdr.snapshot.store.save_snapshot", return_value=tmp_path / "snap.json"),
            patch("aa_auto_sdr.snapshot.git.git_commit_snapshot") as mock_commit,
        ):
            result = single_mod.run_single(
                client=_fake_client(),
                rsid="rs_a",
                formats=["json"],
                output_dir=tmp_path / "out",
                captured_at=_now_utc(),
                tool_version="1.15.0",
                snapshot_dir=tmp_path,
                git_commit=False,
            )

        assert result.git_op is None
        mock_commit.assert_not_called()


class TestDefaultSnapshotDirFallback:
    """P1 regression — --git-commit without --profile should NOT error.

    Before the fix, generate._run_impl and batch._run_impl returned
    ExitCode.CONFIG when profile=None and git_commit=True. They now fall back
    to the "default" profile directory, matching watch.py's behavior.
    """

    def test_generate_git_commit_no_profile_resolves_to_default(self, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import generate as generate_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline import single as single_mod
        from aa_auto_sdr.pipeline.models import RunResult

        ok_result = RunResult(
            rsid="rs_a",
            success=True,
            outputs=[tmp_path / "rs_a.json"],
            report_suite_name="Test Suite",
            git_op=GitOpResult(ok=True, committed=True, commit_sha="a" * 40),
        )

        captured_snapshot_dirs: list[Path] = []

        def fake_run_single(**kwargs):
            captured_snapshot_dirs.append(kwargs.get("snapshot_dir"))
            return ok_result

        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            # Override default_base so the test doesn't touch the real ~/.aa
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(single_mod, "run_single", side_effect=fake_run_single),
        ):
            rc = generate_cmd._run_impl(
                rsid="rs_a",
                output_dir=tmp_path,
                format_name="json",
                profile=None,  # <-- no --profile
                git_commit=True,
                git_push=False,
                git_message=None,
            )

        # Must NOT be CONFIG (10) — must succeed (0)
        assert rc == int(ExitCode.OK), f"expected {int(ExitCode.OK)}, got {rc}"
        # Snapshot dir should resolve to ~/.aa/orgs/default/snapshots
        assert len(captured_snapshot_dirs) == 1
        assert captured_snapshot_dirs[0] is not None
        assert captured_snapshot_dirs[0].parts[-1] == "snapshots"
        assert captured_snapshot_dirs[0].parts[-2] == "default"

    def test_batch_git_commit_no_profile_resolves_to_default(self, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline import batch as batch_mod
        from aa_auto_sdr.pipeline.models import BatchResult, RunResult

        ok_result = RunResult(
            rsid="rs_a",
            success=True,
            outputs=[],
            report_suite_name="Test Suite",
            git_op=GitOpResult(ok=True, committed=True, commit_sha="b" * 40),
        )
        batch_result = BatchResult(
            successes=[ok_result],
            failures=[],
            total_duration_seconds=0.1,
            total_output_bytes=0,
        )

        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(batch_mod, "run_batch", return_value=batch_result),
        ):
            rc = batch_cmd._run_impl(
                rsids=["rs_a"],
                output_dir=tmp_path,
                format_name="json",
                profile=None,  # <-- no --profile
                git_commit=True,
                git_push=False,
                git_message=None,
            )

        # Must NOT be CONFIG (10)
        assert rc == int(ExitCode.OK), f"expected {int(ExitCode.OK)}, got {rc}"


class TestSingleModeGitExitCode:
    def test_run_single_git_failure_returns_snapshot_exit_code(self, tmp_path: Path) -> None:
        """Spec §10 #2 — single-mode git push failure surfaces as ExitCode.SNAPSHOT (16)
        via the generate CLI dispatch layer."""
        from aa_auto_sdr.cli.commands import generate as generate_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline import single as single_mod
        from aa_auto_sdr.pipeline.models import RunResult

        failing_result = RunResult(
            rsid="rs_a",
            success=True,
            outputs=[tmp_path / "rs_a.json"],
            report_suite_name="Test Suite",
            git_op=GitOpResult(
                ok=False,
                committed=True,
                pushed=False,
                commit_sha="x" * 40,
                error_kind="GitPushError",
                error_message="remote rejected",
            ),
        )

        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(single_mod, "run_single", return_value=failing_result),
        ):
            rc = generate_cmd._run_impl(
                rsid="rs_a",
                output_dir=tmp_path,
                format_name="json",
                profile="testprofile",
                git_commit=True,
                git_push=True,
                git_message=None,
            )

        assert rc == int(ExitCode.SNAPSHOT), f"expected {int(ExitCode.SNAPSHOT)}, got {rc}"
        # SNAPSHOT exit code must be 16 per exit_codes.py
        assert int(ExitCode.SNAPSHOT) == 16


class TestBatchModeGit:
    def test_batch_threads_git_flags_to_each_rsid(self, tmp_path: Path) -> None:
        """Each RSID in --batch passes through git_commit/git_push/git_message
        to run_single. Per-RSID commit failures isolate (one fail doesn't
        abort the batch)."""
        from aa_auto_sdr.pipeline import batch as batch_mod
        from aa_auto_sdr.pipeline.models import RunResult

        rsid_results = {
            "rs_a": RunResult(
                rsid="rs_a",
                success=True,
                git_op=GitOpResult(ok=True, committed=True, commit_sha="a" * 40),
            ),
            "rs_b": RunResult(
                rsid="rs_b",
                success=True,
                git_op=GitOpResult(
                    ok=False,
                    committed=True,
                    error_kind="GitPushError",
                    error_message="remote rejected",
                ),
            ),
        }

        captured_kwargs: list[dict] = []

        def fake_run_single(**kwargs):
            captured_kwargs.append(kwargs)
            return rsid_results[kwargs["rsid"]]

        with patch.object(batch_mod, "run_single", side_effect=fake_run_single):
            result = batch_mod.run_batch(
                client=_fake_client(),
                rsids=["rs_a", "rs_b"],
                formats=["json"],
                output_dir=tmp_path,
                captured_at=_now_utc(),
                tool_version="1.15.0",
                snapshot_dir=tmp_path,
                git_commit=True,
                git_push=True,
                git_message=None,
            )

        assert len(captured_kwargs) == 2
        for kw in captured_kwargs:
            assert kw["git_commit"] is True
            assert kw["git_push"] is True
            assert kw["git_message"] is None
        assert len(result.successes) == 2
        assert result.successes[1].git_op.ok is False


class TestBatchModeGitExitCode:
    """P2a regression — batch must not silently exit 0 when git pushes fail.

    Before the fix, per-RSID git failures stashed in RunResult.git_op were
    invisible to the exit-code logic (which only checked BatchResult.failures).
    All SDRs succeed + all git pushes fail → now correctly returns
    PARTIAL_SUCCESS (14) instead of 0.
    """

    def _make_batch_result_with_git_failures(self, tmp_path: Path, *, all_fail: bool):
        """Return a (BatchResult, fake_run_batch) pair where git ops fail."""
        from aa_auto_sdr.pipeline.models import BatchResult, RunResult

        if all_fail:
            successes = [
                RunResult(
                    rsid="rs_a",
                    success=True,
                    outputs=[],
                    git_op=GitOpResult(ok=False, committed=True, error_kind="GitPushError", error_message="no remote"),
                ),
                RunResult(
                    rsid="rs_b",
                    success=True,
                    outputs=[],
                    git_op=GitOpResult(ok=False, committed=True, error_kind="GitPushError", error_message="no remote"),
                ),
            ]
        else:
            successes = [
                RunResult(
                    rsid="rs_a",
                    success=True,
                    outputs=[],
                    git_op=GitOpResult(ok=True, committed=True, commit_sha="a" * 40),
                ),
                RunResult(
                    rsid="rs_b",
                    success=True,
                    outputs=[],
                    git_op=GitOpResult(ok=True, committed=True, commit_sha="b" * 40),
                ),
            ]
        return BatchResult(
            successes=successes,
            failures=[],
            total_duration_seconds=0.1,
            total_output_bytes=0,
        )

    def test_all_sdrs_succeed_all_git_pushes_fail_returns_partial_success(self, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline import batch as batch_mod

        br = self._make_batch_result_with_git_failures(tmp_path, all_fail=True)
        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(batch_mod, "run_batch", return_value=br),
        ):
            rc = batch_cmd._run_impl(
                rsids=["rs_a"],
                output_dir=tmp_path,
                format_name="json",
                profile="testprofile",
                git_commit=True,
                git_push=True,
                git_message=None,
            )

        assert rc == int(ExitCode.PARTIAL_SUCCESS), f"expected PARTIAL_SUCCESS (14), got {rc}"
        assert int(ExitCode.PARTIAL_SUCCESS) == 14

    def test_all_sdrs_succeed_all_git_ops_ok_returns_ok(self, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode
        from aa_auto_sdr.pipeline import batch as batch_mod

        br = self._make_batch_result_with_git_failures(tmp_path, all_fail=False)
        with (
            patch("aa_auto_sdr.core.credentials.resolve", return_value=MagicMock()),
            patch("aa_auto_sdr.api.client.AaClient.from_credentials", return_value=MagicMock()),
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["rs_a"], False)),
            patch("aa_auto_sdr.output.registry.bootstrap"),
            patch("aa_auto_sdr.output.registry.resolve_formats", return_value=["json"]),
            patch("aa_auto_sdr.output.registry.get_writer", return_value=MagicMock()),
            patch("aa_auto_sdr.core.profiles.default_base", return_value=tmp_path),
            patch.object(batch_mod, "run_batch", return_value=br),
        ):
            rc = batch_cmd._run_impl(
                rsids=["rs_a"],
                output_dir=tmp_path,
                format_name="json",
                profile="testprofile",
                git_commit=True,
                git_push=True,
                git_message=None,
            )

        assert rc == int(ExitCode.OK), f"expected OK (0), got {rc}"


# --- helpers ---


def _now_utc():
    return datetime.now(UTC)


def _fake_client():
    return object()


def _fake_sdr_doc(*, rsid: str):
    @dataclass
    class _RS:
        name: str = "test"

    @dataclass
    class _Doc:
        report_suite: _RS = field(default_factory=_RS)
        quality: dict | None = None

        def to_dict(self) -> dict:
            return {"report_suite": {"name": self.report_suite.name}}

    return _Doc()


# --- watch-mode fakes (duplicated from tests/cli/test_watch_command.py) ---


@dataclass
class _WFakeFetcher:
    rsid_to_doc: dict[str, Any] = field(default_factory=dict)
    raise_for: dict[str, BaseException] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def fetch_snapshot(self, rsid: str) -> Any:
        self.calls.append(rsid)
        if rsid in self.raise_for:
            raise self.raise_for[rsid]
        return self.rsid_to_doc.get(rsid, {"rsid": rsid})


@dataclass
class _WFakeStore:
    latest_by_rsid: dict[str, dict | None] = field(default_factory=dict)
    saved: list[tuple[str, Any]] = field(default_factory=list)

    def latest(self, rsid: str) -> dict | None:
        return self.latest_by_rsid.get(rsid)

    def save(self, rsid: str, doc: Any) -> tuple[Path, dict]:
        self.saved.append((rsid, doc))
        path = Path(f"/tmp/{rsid}/{len(self.saved)}.json")
        envelope = {
            "rsid": rsid,
            "captured_at": f"2026-05-11T14:00:0{len(self.saved)}Z",
            "tool_version": "1.15.0",
            "components": {
                "report_suite": {"rsid": rsid, "name": rsid},
                "dimensions": [],
                "metrics": [],
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
            },
        }
        self.latest_by_rsid[rsid] = envelope
        return path, envelope


@dataclass
class _WFakeClock:
    _now: datetime = field(default_factory=lambda: datetime(2026, 5, 11, tzinfo=UTC))

    def utcnow(self) -> datetime:
        out = self._now
        self._now = out + timedelta(seconds=1)
        return out


@dataclass
class _WFakeSleeper:
    calls: list[float] = field(default_factory=list)

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


@dataclass
class _WFakeEmitter:
    events: list[dict] = field(default_factory=list)

    def emit(self, payload: dict) -> None:
        self.events.append(payload)


@dataclass
class _WInjection:
    fetcher: _WFakeFetcher = field(default_factory=_WFakeFetcher)
    store: _WFakeStore = field(default_factory=_WFakeStore)
    clock: _WFakeClock = field(default_factory=_WFakeClock)
    sleeper: _WFakeSleeper = field(default_factory=_WFakeSleeper)
    emitter: _WFakeEmitter = field(default_factory=_WFakeEmitter)


def _make_inj() -> _WInjection:
    return _WInjection()


class TestWatchModeGit:
    def test_watch_emits_error_event_after_change_when_git_fails(self) -> None:
        from aa_auto_sdr.pipeline import watch as watch_mod
        from aa_auto_sdr.pipeline.watch import (
            StopToken,
            WatchContext,
            run_watch_loop,
        )

        inj = _make_inj()
        failing_git = GitOpResult(
            ok=False,
            committed=True,
            pushed=False,
            commit_sha="d" * 40,
            error_kind="GitPushError",
            error_message="remote rejected: refusing to update protected ref",
        )
        with (
            patch.object(watch_mod, "git_commit_snapshot", return_value=failing_git),
        ):
            ctx = WatchContext(
                fetcher=inj.fetcher,
                snapshot_store=inj.store,
                clock=inj.clock,
                sleeper=inj.sleeper,
                emitter=inj.emitter,
                ignore_fields=frozenset(),
                extended_fields=False,
                git_commit=True,
                git_push=True,
                git_message=None,
                snapshot_dir=Path("/tmp/snaps"),
            )
            run_watch_loop(
                ctx=ctx,
                rsids=["rs_a"],
                interval=timedelta(hours=1),
                threshold=0,
                max_cycles=1,
                stop=StopToken(),
            )

        assert len(inj.emitter.events) == 2
        assert inj.emitter.events[0]["event"] == "baseline"
        assert "git" in inj.emitter.events[0]
        assert inj.emitter.events[0]["git"]["committed"] is True
        assert inj.emitter.events[0]["git"]["pushed"] is False
        assert inj.emitter.events[1]["event"] == "error"
        assert inj.emitter.events[1]["error_type"] == "GitPushError"
        assert "rejected" in inj.emitter.events[1]["error"]


class TestWatchThresholdGitsCommitGate:
    """P2b regression — git commits must NOT happen for threshold-suppressed cycles.

    Before the fix, git_commit_snapshot was called inside run_one_cycle for
    every baseline/diffed cycle regardless of the --watch-threshold gate.
    Now _maybe_commit is called after _should_emit inside run_watch_loop, so
    suppressed cycles never generate commits.
    """

    def _make_watch_ctx(self, inj: _WInjection, *, git_commit_mock):  # type: ignore[return]
        from aa_auto_sdr.pipeline.watch import WatchContext

        return WatchContext(
            fetcher=inj.fetcher,
            snapshot_store=inj.store,
            clock=inj.clock,
            sleeper=inj.sleeper,
            emitter=inj.emitter,
            ignore_fields=frozenset(),
            extended_fields=False,
            git_commit=True,
            git_push=False,
            git_message=None,
            snapshot_dir=Path("/tmp/snaps"),
        )

    def test_git_commit_not_called_when_cycle_suppressed_by_threshold(self) -> None:
        """Threshold=5, diff has 1 change → cycle suppressed → git MUST NOT commit."""
        from unittest.mock import MagicMock, patch

        from aa_auto_sdr.pipeline import watch as watch_mod
        from aa_auto_sdr.pipeline.watch import StopToken, run_watch_loop
        from aa_auto_sdr.snapshot.models import AddedRemovedItem, ComponentDiff, DiffReport

        inj = _make_inj()
        # Seed the store so cycle 0 is a baseline (always emitted), then cycle 1
        # produces a 1-change diff that threshold=5 suppresses.
        # We need a second doc to force a diff on cycle 1.
        call_count = 0

        def fetch_rotating(rsid: str) -> Any:
            nonlocal call_count
            call_count += 1
            return {"rsid": rsid, "call": call_count}

        inj.fetcher.fetch_snapshot = fetch_rotating  # type: ignore[assignment]

        git_mock = MagicMock(return_value=GitOpResult(ok=True, committed=True, commit_sha="a" * 40))

        # Patch compare so cycle 1 produces exactly 1 change.
        small_diff = DiffReport(
            a_rsid="rs_a",
            b_rsid="rs_a",
            a_captured_at="X",
            b_captured_at="Y",
            a_tool_version="1.15.0",
            b_tool_version="1.15.0",
            components=[
                ComponentDiff(
                    component_type="dimensions",
                    added=[AddedRemovedItem(id="a0", name="a0")],
                    removed=[],
                    modified=[],
                    unchanged_count=0,
                )
            ],
        )

        with (
            patch.object(watch_mod, "git_commit_snapshot", git_mock),
            patch.object(watch_mod, "compare", return_value=small_diff),
        ):
            ctx = self._make_watch_ctx(inj, git_commit_mock=git_mock)
            run_watch_loop(
                ctx=ctx,
                rsids=["rs_a"],
                interval=__import__("datetime").timedelta(seconds=0),
                threshold=5,  # 1 change < 5 → cycle 1 suppressed
                max_cycles=2,
                stop=StopToken(),
            )

        # Cycle 0 is a baseline → always emits → git commits.
        # Cycle 1 is a 1-change diff suppressed by threshold=5 → no git commit.
        # So git_commit_snapshot must be called exactly ONCE (for the baseline).
        assert git_mock.call_count == 1, (
            f"expected 1 git commit (baseline only), got {git_mock.call_count}"
        )
        # Only the baseline event emitted.
        assert len(inj.emitter.events) == 1
        assert inj.emitter.events[0]["event"] == "baseline"

    def test_git_commit_called_when_cycle_meets_threshold(self) -> None:
        """Threshold=0 → every cycle emits → git MUST commit for each one."""
        from unittest.mock import MagicMock, patch

        from aa_auto_sdr.pipeline import watch as watch_mod
        from aa_auto_sdr.pipeline.watch import StopToken, run_watch_loop

        inj = _make_inj()
        call_count = 0

        def fetch_rotating(rsid: str) -> Any:
            nonlocal call_count
            call_count += 1
            return {"rsid": rsid, "call": call_count}

        inj.fetcher.fetch_snapshot = fetch_rotating  # type: ignore[assignment]

        git_mock = MagicMock(return_value=GitOpResult(ok=True, committed=True, commit_sha="a" * 40))

        with (
            patch.object(watch_mod, "git_commit_snapshot", git_mock),
        ):
            ctx = self._make_watch_ctx(inj, git_commit_mock=git_mock)
            run_watch_loop(
                ctx=ctx,
                rsids=["rs_a"],
                interval=__import__("datetime").timedelta(seconds=0),
                threshold=0,  # emit every cycle
                max_cycles=2,
                stop=StopToken(),
            )

        # Both cycle 0 (baseline) and cycle 1 (diffed) emit → both commit.
        assert git_mock.call_count == 2, (
            f"expected 2 git commits (one per emitted cycle), got {git_mock.call_count}"
        )
