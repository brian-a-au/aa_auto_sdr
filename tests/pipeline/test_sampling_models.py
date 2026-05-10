"""BatchResult sampling fields (v1.10.0)."""

from __future__ import annotations

from aa_auto_sdr.pipeline.models import BatchResult


class TestBatchResultSamplingFields:
    def test_defaults_are_unsampled(self) -> None:
        result = BatchResult()
        assert result.sampled is False
        assert result.sample_size is None
        assert result.sample_seed is None
        assert result.total_available == 0

    def test_construct_sampled(self) -> None:
        result = BatchResult(
            sampled=True,
            sample_size=5,
            sample_seed=42,
            total_available=200,
        )
        assert result.sampled is True
        assert result.sample_size == 5
        assert result.sample_seed == 42
        assert result.total_available == 200

    def test_existing_fields_still_default(self) -> None:
        # Regression lock — adding sampling fields must not perturb pre-v1.10 defaults.
        result = BatchResult()
        assert result.successes == []
        assert result.failures == []
        assert result.total_duration_seconds == 0.0
        assert result.total_output_bytes == 0
        assert result.batch_id == ""
