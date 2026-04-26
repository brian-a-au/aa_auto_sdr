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
