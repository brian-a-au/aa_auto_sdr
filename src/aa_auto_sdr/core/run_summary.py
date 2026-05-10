"""RunSummary: structured outcome of a generate/batch run, suitable for JSON emit.

Built at end of run by cli/commands/{generate,batch}.py and emitted as JSON
when --run-summary-json is set (PATH for a file, '-' for stdout). The flag is
wired in v1.2.1; the dataclass shape was added in v1.2.0."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class PerRsidResult:
    rsid: str
    name: str | None
    succeeded: bool
    formats: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    snapshot_path: str | None = None
    error: str | None = None
    # v1.12.0 — quality verdict from the gate. "" when no audits ran;
    # "pass" / "fail" / "n/a" when audits + --fail-on-quality were active.
    quality_verdict: str = ""


@dataclass(frozen=True, slots=True)
class RunSummary:
    started_at: str  # ISO-8601
    finished_at: str
    duration_seconds: float
    tool_version: str
    profile: str | None
    rsids: list[PerRsidResult]
    timings: list[tuple[str, float]] = field(default_factory=list)
    # v1.10.0 — sampling fields surfaced for JSON-summary consumers. Mirror the
    # shape of BatchResult so callers can branch on `sampled` and read the rest.
    # Defaults preserve backward compatibility with generate (single-RSID) runs,
    # which never sample.
    sampled: bool = False
    sample_size: int | None = None
    sample_seed: int | None = None
    sample_strategy: str | None = None
    total_available: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        # Coerce timing tuples to lists for JSON-friendliness; json.dumps would
        # do this anyway, but we want round-trip equality without serializing.
        d["timings"] = [list(t) for t in d["timings"]]
        return d
