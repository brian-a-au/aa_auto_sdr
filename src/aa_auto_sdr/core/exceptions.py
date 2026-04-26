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


class ReportSuiteNotFoundError(AaAutoSdrError):
    """The requested RSID does not exist in this org."""


class SnapshotError(AaAutoSdrError):
    """Base for snapshot-related errors."""


class SnapshotResolveError(SnapshotError):
    """A snapshot identifier (path, RSID@ts, git ref) could not be resolved."""


class SnapshotSchemaError(SnapshotError):
    """A snapshot file's schema is unknown or unsupported."""


class OutputError(AaAutoSdrError):
    """An output writer failed (I/O, formatting, etc.)."""
