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
