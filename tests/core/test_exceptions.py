"""Verify the exception hierarchy is shaped as the design spec requires."""

import pytest

from aa_auto_sdr.core import exceptions as exc
from aa_auto_sdr.core.exceptions import ApiError, TransientApiError


def test_base_class_is_aaautosdrerror() -> None:
    assert issubclass(exc.AaAutoSdrError, Exception)


@pytest.mark.parametrize(
    "child",
    [
        exc.ConfigError,
        exc.AuthError,
        exc.ApiError,
        exc.ReportSuiteNotFoundError,
        exc.SnapshotError,
        exc.OutputError,
    ],
)
def test_top_level_children_inherit_base(child: type[Exception]) -> None:
    assert issubclass(child, exc.AaAutoSdrError)


def test_unsupported_by_api20_is_apierror() -> None:
    assert issubclass(exc.UnsupportedByApi20, exc.ApiError)


@pytest.mark.parametrize(
    "child",
    [exc.SnapshotResolveError, exc.SnapshotSchemaError],
)
def test_snapshot_children_inherit_snapshoterror(child: type[Exception]) -> None:
    assert issubclass(child, exc.SnapshotError)


def test_transient_api_error_is_api_error_subclass() -> None:
    """TransientApiError must subclass ApiError so the CLI's existing
    except-ApiError catches treat it as an API failure (exit 12)."""
    assert issubclass(TransientApiError, ApiError)
    err = TransientApiError("transient")
    assert isinstance(err, ApiError)
