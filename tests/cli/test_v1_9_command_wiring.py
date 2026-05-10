"""v1.9.0 audit/stale flags reach build_sdr through CLI → pipeline.

See spec §3.7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from aa_auto_sdr.pipeline import single
from aa_auto_sdr.pipeline.batch import run_batch
from aa_auto_sdr.pipeline.models import BatchResult


def _empty_batch_result() -> BatchResult:
    return BatchResult(
        successes=[],
        failures=[],
        total_duration_seconds=0.0,
        total_output_bytes=0,
        batch_id="testbid",
    )


def test_run_single_threads_audit_naming(tmp_path: Path) -> None:
    mock_writer = MagicMock()
    mock_writer.extension = ".json"
    mock_writer.write.return_value = []
    with (
        patch("aa_auto_sdr.pipeline.single.build_sdr") as build,
        patch("aa_auto_sdr.pipeline.single.registry") as mock_registry,
    ):
        mock_registry.get_writer.return_value = mock_writer
        build.return_value = MagicMock(
            report_suite=MagicMock(name="rs1"),
            outputs=[],
            duration_seconds=0,
        )
        single.run_single(
            client=MagicMock(),
            rsid="rs1",
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 5, 9, tzinfo=UTC),
            tool_version="1.9.0",
            audit_naming=True,
        )
        kwargs = build.call_args.kwargs
        assert kwargs["audit_naming"] is True
        assert kwargs.get("flag_stale", False) is False


def test_run_single_threads_flag_stale(tmp_path: Path) -> None:
    mock_writer = MagicMock()
    mock_writer.extension = ".json"
    mock_writer.write.return_value = []
    with (
        patch("aa_auto_sdr.pipeline.single.build_sdr") as build,
        patch("aa_auto_sdr.pipeline.single.registry") as mock_registry,
    ):
        mock_registry.get_writer.return_value = mock_writer
        build.return_value = MagicMock(
            report_suite=MagicMock(name="rs1"),
            outputs=[],
            duration_seconds=0,
        )
        single.run_single(
            client=MagicMock(),
            rsid="rs1",
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 5, 9, tzinfo=UTC),
            tool_version="1.9.0",
            flag_stale=True,
        )
        kwargs = build.call_args.kwargs
        assert kwargs["flag_stale"] is True


def test_run_batch_threads_audit_and_stale_to_run_parallel(tmp_path: Path) -> None:
    with patch("aa_auto_sdr.pipeline.batch.run_parallel") as par:
        par.return_value = _empty_batch_result()
        run_batch(
            client=MagicMock(),
            rsids=["r1", "r2"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 5, 9, tzinfo=UTC),
            tool_version="1.9.0",
            workers=2,
            audit_naming=True,
            flag_stale=True,
        )
        kwargs = par.call_args.kwargs
        assert kwargs["audit_naming"] is True
        assert kwargs["flag_stale"] is True


def test_run_batch_default_no_audit_no_stale(tmp_path: Path) -> None:
    """Backward compat: omitting flags reaches run_parallel as False."""
    with patch("aa_auto_sdr.pipeline.batch.run_parallel") as par:
        par.return_value = _empty_batch_result()
        run_batch(
            client=MagicMock(),
            rsids=["r1", "r2"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 5, 9, tzinfo=UTC),
            tool_version="1.9.0",
            workers=2,
        )
        kwargs = par.call_args.kwargs
        assert kwargs.get("audit_naming", False) is False
        assert kwargs.get("flag_stale", False) is False


def test_run_batch_sequential_path_threads_audit_naming(tmp_path: Path) -> None:
    """workers=1 (sequential path) also threads audit_naming/flag_stale to single.run_single."""
    with patch("aa_auto_sdr.pipeline.batch.single.run_single") as run_single_mock:
        from aa_auto_sdr.pipeline.models import RunResult

        run_single_mock.return_value = RunResult(
            rsid="r1",
            success=True,
            duration_seconds=0.0,
            outputs=[],
        )
        run_batch(
            client=MagicMock(),
            rsids=["r1"],
            formats=["json"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 5, 9, tzinfo=UTC),
            tool_version="1.9.0",
            workers=1,
            audit_naming=True,
        )
        kwargs = run_single_mock.call_args.kwargs
        assert kwargs["audit_naming"] is True
