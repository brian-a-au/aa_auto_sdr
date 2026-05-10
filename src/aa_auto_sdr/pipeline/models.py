"""Pipeline result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunResult:
    rsid: str
    success: bool
    outputs: list[Path] = field(default_factory=list)
    error: str | None = None
    report_suite_name: str | None = None
    duration_seconds: float = 0.0
    # v1.12.0 — quality gate / report. `quality_verdict` is one of
    # "pass" / "fail" / "n/a" / "" (empty when no audit ran).
    quality_verdict: str = ""
    quality_report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class BatchFailure:
    """Per-RSID failure record for a batch run."""

    rsid: str
    error_type: str  # "ApiError", "ReportSuiteNotFoundError", etc.
    message: str  # exception's str()
    exit_code: int  # the exit code single-RSID would have returned


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Aggregated outcome of a sequential batch run."""

    successes: list[RunResult] = field(default_factory=list)
    failures: list[BatchFailure] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    total_output_bytes: int = 0
    batch_id: str = ""
    # v1.10.0 — sampling. `total_available` is the input RSID count regardless
    # of whether sampling actually fired; consumers should pair it with `sampled`
    # to know if the value is "before sampling" or just "the dispatched set".
    sampled: bool = False
    sample_size: int | None = None
    sample_seed: int | None = None
    sample_strategy: str | None = None  # "random" or "stratified" when sampled
    total_available: int = 0
    # v1.12.0 — per-RSID quality verdicts. Empty when --fail-on-quality not set.
    quality_verdicts: dict[str, str] = field(default_factory=dict)
