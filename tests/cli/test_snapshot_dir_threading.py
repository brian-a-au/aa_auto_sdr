"""Tests for the shared --snapshot-dir resolver.

This module pins the resolver precedence (--snapshot-dir > profile > "default")
across generate/batch/watch dispatch. Lives in tests/cli/ because the resolver
is a CLI-layer helper that reads argparse Namespaces.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _ns(**kwargs) -> argparse.Namespace:
    """Build a Namespace with the keys the resolver reads. Anything not set
    falls back via getattr(..., None)."""
    return argparse.Namespace(**kwargs)


class TestResolveSnapshotDir:
    def test_explicit_snapshot_dir_wins(self, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands._shared import resolve_snapshot_dir

        explicit = tmp_path / "explicit"
        ns = _ns(snapshot_dir=str(explicit), profile="acme")
        assert resolve_snapshot_dir(ns) == Path(explicit)

    def test_profile_used_when_no_snapshot_dir(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import _shared
        from aa_auto_sdr.core import profiles

        monkeypatch.setattr(profiles, "default_base", lambda: tmp_path / ".aa")
        ns = _ns(snapshot_dir=None, profile="acme")
        assert _shared.resolve_snapshot_dir(ns) == tmp_path / ".aa" / "orgs" / "acme" / "snapshots"

    def test_default_profile_when_neither_set(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.cli.commands import _shared
        from aa_auto_sdr.core import profiles

        monkeypatch.setattr(profiles, "default_base", lambda: tmp_path / ".aa")
        ns = _ns(snapshot_dir=None, profile=None)
        assert _shared.resolve_snapshot_dir(ns) == tmp_path / ".aa" / "orgs" / "default" / "snapshots"


class TestGenerateHonorsSnapshotDir:
    def test_generate_passes_explicit_snapshot_dir_to_pipeline(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.api import fetch as fetch_mod
        from aa_auto_sdr.api.client import AaClient
        from aa_auto_sdr.cli.commands import generate
        from aa_auto_sdr.core import credentials
        from aa_auto_sdr.pipeline import single as single_mod
        from aa_auto_sdr.pipeline.models import RunResult

        captured: dict[str, object] = {}

        def _fake_run_single(**kwargs):
            captured["snapshot_dir"] = kwargs.get("snapshot_dir")
            return RunResult(
                rsid=kwargs["rsid"],
                success=True,
                outputs=[],
                report_suite_name="stub",
                git_op=None,
            )

        monkeypatch.setattr(single_mod, "run_single", _fake_run_single)
        monkeypatch.setattr(credentials, "resolve", lambda profile=None: object())  # noqa: ARG005
        monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, *a, **kw: object()))  # noqa: ARG005
        monkeypatch.setattr(fetch_mod, "resolve_rsid", lambda *a, **kw: (["rs_a"], False))  # noqa: ARG005

        explicit = tmp_path / "explicit"
        rc = generate.run(
            rsid="rs_a",
            output_dir=tmp_path / "out",
            format_name="json",
            profile=None,
            git_commit=True,
            snapshot_dir=explicit,
        )
        assert rc == 0
        assert captured["snapshot_dir"] == explicit

    def test_generate_runs_without_snapshot_dir_when_no_save_required(self, monkeypatch, tmp_path: Path) -> None:
        """No --git-commit / --snapshot / --auto-snapshot → snapshot_dir is None."""
        from aa_auto_sdr.api import fetch as fetch_mod
        from aa_auto_sdr.api.client import AaClient
        from aa_auto_sdr.cli.commands import generate
        from aa_auto_sdr.core import credentials
        from aa_auto_sdr.pipeline import single as single_mod
        from aa_auto_sdr.pipeline.models import RunResult

        captured: dict[str, object] = {}

        def _fake_run_single(**kwargs):
            captured["snapshot_dir"] = kwargs.get("snapshot_dir")
            return RunResult(
                rsid=kwargs["rsid"],
                success=True,
                outputs=[],
                report_suite_name="stub",
                git_op=None,
            )

        monkeypatch.setattr(single_mod, "run_single", _fake_run_single)
        monkeypatch.setattr(credentials, "resolve", lambda profile=None: object())  # noqa: ARG005
        monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, *a, **kw: object()))  # noqa: ARG005
        monkeypatch.setattr(fetch_mod, "resolve_rsid", lambda *a, **kw: (["rs_a"], False))  # noqa: ARG005

        rc = generate.run(
            rsid="rs_a",
            output_dir=tmp_path / "out",
            format_name="json",
            profile=None,
            git_commit=False,
            snapshot_dir=None,
        )
        assert rc == 0
        assert captured["snapshot_dir"] is None


class TestGenerateCliBoundaryThreadsSnapshotDir:
    def test_main_passes_resolver_output_to_generate(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.cli import main as main_mod
        from aa_auto_sdr.cli.commands import generate

        captured: dict[str, object] = {}

        def _fake_generate_run(**kwargs):
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(generate, "run", _fake_generate_run)
        explicit = tmp_path / "explicit"
        rc = main_mod.run(
            [
                "rs_a",
                "--git-commit",
                "--snapshot-dir",
                str(explicit),
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        assert rc == 0
        assert captured["snapshot_dir"] == explicit


class TestBatchHonorsSnapshotDir:
    def test_batch_passes_explicit_snapshot_dir_to_runner(self, monkeypatch, tmp_path: Path) -> None:
        from aa_auto_sdr.api import fetch as fetch_mod
        from aa_auto_sdr.api.client import AaClient
        from aa_auto_sdr.cli.commands import batch
        from aa_auto_sdr.core import credentials
        from aa_auto_sdr.pipeline import batch as batch_runner
        from aa_auto_sdr.pipeline.models import BatchResult

        captured: dict[str, object] = {}

        def _fake_run_batch(**kwargs):
            captured["snapshot_dir"] = kwargs.get("snapshot_dir")
            return BatchResult(successes=[], failures=[])

        monkeypatch.setattr(batch_runner, "run_batch", _fake_run_batch)
        monkeypatch.setattr(credentials, "resolve", lambda profile=None: object())  # noqa: ARG005
        monkeypatch.setattr(
            AaClient,
            "from_credentials",
            classmethod(lambda cls, *a, **kw: object()),  # noqa: ARG005
        )
        monkeypatch.setattr(fetch_mod, "resolve_rsid", lambda *a, **kw: (["rs_a"], False))  # noqa: ARG005

        explicit = tmp_path / "explicit"
        rc = batch.run(
            rsids=["rs_a", "rs_b"],
            output_dir=tmp_path / "out",
            format_name="excel",
            profile=None,
            git_commit=True,
            snapshot_dir=explicit,
        )
        assert rc == 0
        assert captured["snapshot_dir"] == explicit


class TestExplicitSnapshotDirReachesPipeline:
    def test_explicit_snapshot_dir_propagates_to_single_pipeline(self, monkeypatch, tmp_path: Path) -> None:
        """End-to-end at the cli/main.py boundary: --snapshot-dir /tmp/explicit/
        + --git-commit on a single RSID surfaces /tmp/explicit/ as the
        snapshot_dir passed into pipeline.single.run_single. This pins the
        wiring that determines where the lazy git auto-init happens (the
        actual auto-init is exercised by tests/pipeline/test_git_integration.py
        and live smoke)."""
        from aa_auto_sdr.api import fetch as fetch_mod
        from aa_auto_sdr.api.client import AaClient
        from aa_auto_sdr.cli import main as main_mod
        from aa_auto_sdr.core import credentials
        from aa_auto_sdr.pipeline import single as single_mod
        from aa_auto_sdr.pipeline.models import RunResult
        from aa_auto_sdr.snapshot.git import GitOpResult

        seen: dict[str, Path | None] = {}

        def _fake_run_single(**kwargs):
            seen["snapshot_dir"] = kwargs.get("snapshot_dir")
            return RunResult(
                rsid=kwargs["rsid"],
                success=True,
                outputs=[],
                report_suite_name="stub",
                git_op=GitOpResult(
                    ok=True,
                    committed=True,
                    commit_sha="deadbeef",
                    pushed=False,
                    error_kind=None,
                    error_message=None,
                ),
            )

        monkeypatch.setattr(single_mod, "run_single", _fake_run_single)
        monkeypatch.setattr(credentials, "resolve", lambda profile=None: object())  # noqa: ARG005
        monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, *a, **kw: object()))  # noqa: ARG005
        monkeypatch.setattr(fetch_mod, "resolve_rsid", lambda *a, **kw: (["rs_a"], False))  # noqa: ARG005

        explicit = tmp_path / "explicit"
        rc = main_mod.run(
            [
                "rs_a",
                "--git-commit",
                "--snapshot-dir",
                str(explicit),
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        assert rc == 0
        assert seen["snapshot_dir"] == explicit
