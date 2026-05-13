"""Typed exception hierarchy. See design spec §6."""


class AaAutoSdrError(Exception):
    """Base class for all aa_auto_sdr errors."""


class ConfigError(AaAutoSdrError):
    """Bad config or missing credentials."""


class AuthError(AaAutoSdrError):
    """OAuth Server-to-Server failure."""


class ApiError(AaAutoSdrError):
    """Network or API-level error."""


class UnsupportedByApi20(ApiError):
    """Raised when a feature is only available in the legacy 1.4 API.

    The 1.4 API is explicitly out of scope; surface this rather than degrading.
    """


class TransientApiError(ApiError):
    """Retryable transient API failure surfaced through the AA SDK boundary.

    Per `docs/superpowers/spikes/2026-05-08-aanalytics2-resilience-spike.md`,
    `aanalytics2` 0.5.1 sets `urllib3.Retry(raise_on_status=False)` which
    swallows non-2xx responses into stub dicts. Downstream SDK code then
    indexes into those stubs and raises `KeyError`/`ValueError`. The
    `_retry_and_normalize` helper in `api/fetch.py` catches that pattern
    and re-raises as `TransientApiError` so `is_retryable` (in
    `api/resilience.py`) can dispatch on a typed signal rather than
    guessing about exception classes that the SDK never actually emits.
    """


class VrsEndpointShapeError(ApiError):
    """Adobe Analytics VRS-list endpoint returned a malformed/empty envelope.

    Permanent failure mode (for the duration of the run) where the SDK
    indexes `vrsid['content']` on a response that lacks that key — the
    pattern documented in
    `docs/superpowers/spikes/2026-05-12-vrs-probe-script.md` and observed
    in the field on tenants with zero VRS. Distinct from
    `TransientApiError` so the resilience layer's retry policy skips it.
    """


class ReportSuiteNotFoundError(AaAutoSdrError):
    """The requested RSID does not exist in this org."""


class AmbiguousMatchError(AaAutoSdrError):
    """Raised when a name token resolves to multiple report suites in
    non-interactive mode. `candidates` is a list of (rsid, name) tuples.

    Maps to ExitCode.NOT_FOUND for CLI exit-code parity with the
    existing ReportSuiteNotFoundError; the distinct class lets the CLI
    render candidate lists differently (one match required).
    """

    def __init__(self, message: str, candidates: list[tuple[str, str]]) -> None:
        super().__init__(message)
        self.candidates = candidates


class SnapshotError(AaAutoSdrError):
    """Base for snapshot-related errors."""


class SnapshotResolveError(SnapshotError):
    """A snapshot identifier (path, RSID@ts, git ref) could not be resolved."""


class SnapshotSchemaError(SnapshotError):
    """A snapshot file's schema is unknown or unsupported."""


class OutputError(AaAutoSdrError):
    """An output writer failed (I/O, formatting, etc.)."""
