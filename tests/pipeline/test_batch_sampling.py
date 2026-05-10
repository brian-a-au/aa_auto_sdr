"""run_batch sampling wiring (v1.10.0)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.pipeline import batch as batch_runner
from aa_auto_sdr.pipeline.models import BatchResult, RunResult


def _stub_run_single(**kwargs: object) -> RunResult:
    rsid = kwargs["rsid"]
    assert isinstance(rsid, str)
    return RunResult(
        rsid=rsid,
        success=True,
        outputs=[],
        report_suite_name=None,
        duration_seconds=0.0,
    )


@pytest.fixture
def common_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "client": MagicMock(),
        "formats": ["json"],
        "output_dir": tmp_path,
        "captured_at": datetime.now(UTC),
        "tool_version": "1.10.0",
    }


class TestRunBatchSampling:
    def test_unsampled_run_records_total_available(self, common_kwargs: dict[str, object]) -> None:
        rsids = [f"rs{i}" for i in range(5)]
        with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=_stub_run_single):
            result = batch_runner.run_batch(rsids=rsids, **common_kwargs)
        assert isinstance(result, BatchResult)
        assert result.sampled is False
        assert result.sample_size is None
        assert result.sample_seed is None
        assert result.total_available == 5
        assert len(result.successes) == 5

    def test_sampled_run_subsets_rsids(self, common_kwargs: dict[str, object]) -> None:
        rsids = [f"rs{i}" for i in range(20)]
        with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=_stub_run_single):
            result = batch_runner.run_batch(
                rsids=rsids,
                sample_size=5,
                sample_seed=42,
                **common_kwargs,
            )
        assert result.sampled is True
        assert result.sample_size == 5
        assert result.sample_seed == 42
        assert result.total_available == 20
        assert len(result.successes) == 5

    def test_sample_size_ge_total_is_no_op(self, common_kwargs: dict[str, object]) -> None:
        rsids = [f"rs{i}" for i in range(3)]
        with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=_stub_run_single):
            result = batch_runner.run_batch(
                rsids=rsids,
                sample_size=99,
                **common_kwargs,
            )
        assert result.sampled is False
        assert result.sample_size is None
        assert result.total_available == 3
        assert len(result.successes) == 3

    def test_sample_seed_reproducibility(self, common_kwargs: dict[str, object]) -> None:
        rsids = [f"rs{i}" for i in range(20)]
        with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=_stub_run_single):
            a = batch_runner.run_batch(rsids=rsids, sample_size=5, sample_seed=7, **common_kwargs)
            b = batch_runner.run_batch(rsids=rsids, sample_size=5, sample_seed=7, **common_kwargs)
        a_rsids = sorted(r.rsid for r in a.successes)
        b_rsids = sorted(r.rsid for r in b.successes)
        assert a_rsids == b_rsids

    def test_stratified_flag_reaches_sampler(self, common_kwargs: dict[str, object]) -> None:
        rsids = [f"prod_{i}" for i in range(5)] + [f"dev_{i}" for i in range(5)]
        with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=_stub_run_single):
            result = batch_runner.run_batch(
                rsids=rsids,
                sample_size=4,
                sample_seed=0,
                sample_stratified=True,
                **common_kwargs,
            )
        assert result.sampled is True
        assert result.sample_size == 4
        from aa_auto_sdr.pipeline.sampling import _prefix_of

        prefixes = {_prefix_of(r.rsid) for r in result.successes}
        # Stratified with both groups present given proportional allocation.
        assert prefixes == {"prod", "dev"}

    def test_sampling_runs_before_workers_dispatch(self, common_kwargs: dict[str, object]) -> None:
        # workers=2 still operates on the sampled subset.
        rsids = [f"rs{i}" for i in range(20)]
        with patch("aa_auto_sdr.pipeline.batch.single.run_single", side_effect=_stub_run_single):
            result = batch_runner.run_batch(
                rsids=rsids,
                sample_size=4,
                sample_seed=1,
                workers=2,
                **common_kwargs,
            )
        assert result.sampled is True
        assert len(result.successes) == 4


class TestRunBatchSamplingValidation:
    def test_sample_size_zero_raises(self, common_kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError, match=r"sample_size must be >= 1"):
            batch_runner.run_batch(rsids=["a", "b"], sample_size=0, **common_kwargs)

    def test_sample_size_negative_raises(self, common_kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError, match=r"sample_size must be >= 1"):
            batch_runner.run_batch(rsids=["a", "b"], sample_size=-3, **common_kwargs)
