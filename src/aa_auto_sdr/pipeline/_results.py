"""Shared batch outcome accounting for sequential, parallel, and CLI paths."""

from __future__ import annotations

import os

from aa_auto_sdr.core.exceptions import (
    AaAutoSdrError,
    ApiError,
    AuthError,
    ConfigError,
    OutputError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.pipeline.models import RunResult

_EXIT_CODE_BY_TYPE: dict[type[AaAutoSdrError], int] = {
    ConfigError: ExitCode.CONFIG.value,
    AuthError: ExitCode.AUTH.value,
    ApiError: ExitCode.API.value,
    ReportSuiteNotFoundError: ExitCode.NOT_FOUND.value,
    OutputError: ExitCode.OUTPUT.value,
}


def error_exit_code(exc: AaAutoSdrError) -> int:
    """Match the single-run policy; most-specific class wins."""
    for cls in type(exc).__mro__:
        if cls in _EXIT_CODE_BY_TYPE:
            return _EXIT_CODE_BY_TYPE[cls]
    return ExitCode.GENERIC.value


def output_bytes(result: RunResult) -> int:
    """Sum output sizes, tolerating files removed since generation."""
    total = 0
    for path in result.outputs:
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return total
