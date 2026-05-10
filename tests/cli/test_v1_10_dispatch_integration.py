"""End-to-end CLI dispatch + banner test for v1.10.0 sampling.

Catches the regression class where _run_impl reconstructs BatchResult
and silently drops sampling fields before reaching _print_summary.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import batch as batch_command
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.pipeline.models import BatchFailure, BatchResult, RunResult


def _stub_batch_result(*, sampled: bool = True, batch_id: str = "test_batch") -> BatchResult:
    return BatchResult(
        successes=[
            RunResult(
                rsid="rs1",
                success=True,
                outputs=[],
                report_suite_name=None,
                duration_seconds=0.1,
            ),
        ],
        failures=[],
        total_duration_seconds=0.1,
        total_output_bytes=0,
        batch_id=batch_id,
        sampled=sampled,
        sample_size=2 if sampled else None,
        sample_seed=42 if sampled else None,
        sample_strategy="random" if sampled else None,
        total_available=10 if sampled else 1,
    )


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


class TestSamplingFieldsReachBanner:
    """Regression tests: sampling fields must survive _run_impl's reconstruction."""

    def test_sampled_run_banner_contains_sampled_line(
        self,
        env_creds: None,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        with (
            patch.object(
                batch_command.batch_runner,
                "run_batch",
                return_value=_stub_batch_result(sampled=True),
            ),
            patch.object(batch_command.fetch, "resolve_rsid", return_value=(["rs1"], False)),
            patch.object(batch_command.AaClient, "from_credentials", return_value=MagicMock()),
        ):
            exit_code = batch_command.run(
                rsids=["rs1", "rs2"],
                output_dir=tmp_path,
                format_name="json",
                profile=None,
                sample_size=2,
                sample_seed=42,
            )

        assert exit_code == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "Sampled 2 of 10 RSIDs" in out, f"Banner missing sampled line. stdout was: {out!r}"
        assert "seed=42" in out

    def test_unsampled_run_banner_omits_sampled_line(
        self,
        env_creds: None,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        with (
            patch.object(
                batch_command.batch_runner,
                "run_batch",
                return_value=_stub_batch_result(sampled=False),
            ),
            patch.object(batch_command.fetch, "resolve_rsid", return_value=(["rs1"], False)),
            patch.object(batch_command.AaClient, "from_credentials", return_value=MagicMock()),
        ):
            exit_code = batch_command.run(
                rsids=["rs1", "rs2"],
                output_dir=tmp_path,
                format_name="json",
                profile=None,
            )

        assert exit_code == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "Sampled" not in out

    def test_batch_id_survives_reconstruction(
        self,
        env_creds: None,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Pre-v1.10.0 latent bug: batch_id was being dropped too.

        Fix to Critical #1 (dataclasses.replace) also fixes this. Lock the regression.
        """
        with (
            patch.object(
                batch_command.batch_runner,
                "run_batch",
                return_value=_stub_batch_result(sampled=False),
            ),
            patch.object(batch_command.fetch, "resolve_rsid", return_value=(["rs1"], False)),
            patch.object(batch_command.AaClient, "from_credentials", return_value=MagicMock()),
        ):
            received: list[BatchResult] = []
            original_print_summary = batch_command._print_summary

            def capture(result: BatchResult) -> None:
                received.append(result)
                original_print_summary(result)

            with patch.object(batch_command, "_print_summary", side_effect=capture):
                batch_command.run(
                    rsids=["rs1", "rs2"],
                    output_dir=tmp_path,
                    format_name="json",
                    profile=None,
                )

        assert received, "_print_summary was not called"
        assert received[0].batch_id == "test_batch", (
            f"batch_id dropped during reconstruction. Got: {received[0].batch_id!r}"
        )

    def test_pre_failures_merge_preserves_sampling_fields(
        self,
        env_creds: None,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """When pre_failures are merged into final, sampling fields must persist."""

        # Make rs2 fail to resolve so a pre_failure is added. resolve_rsid is
        # called per identifier; first call returns rs1, second raises.
        from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

        call_count = {"n": 0}

        def fake_resolve(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (["rs1"], False)
            raise ReportSuiteNotFoundError("rs2 not found")

        with (
            patch.object(
                batch_command.batch_runner,
                "run_batch",
                return_value=_stub_batch_result(sampled=True),
            ),
            patch.object(batch_command.fetch, "resolve_rsid", side_effect=fake_resolve),
            patch.object(batch_command.AaClient, "from_credentials", return_value=MagicMock()),
        ):
            received: list[BatchResult] = []
            original_print_summary = batch_command._print_summary

            def capture(result: BatchResult) -> None:
                received.append(result)
                original_print_summary(result)

            with patch.object(batch_command, "_print_summary", side_effect=capture):
                batch_command.run(
                    rsids=["rs1", "rs2"],
                    output_dir=tmp_path,
                    format_name="json",
                    profile=None,
                    sample_size=2,
                    sample_seed=42,
                )

        assert received, "_print_summary was not called"
        final = received[0]
        # Critical: sampling fields survived the failures-merge step.
        assert final.sampled is True
        assert final.sample_size == 2
        assert final.sample_seed == 42
        assert final.sample_strategy == "random"
        assert final.total_available == 10
        assert final.batch_id == "test_batch"
        # And the pre_failure was actually merged in.
        assert any(isinstance(f, BatchFailure) for f in final.failures)
