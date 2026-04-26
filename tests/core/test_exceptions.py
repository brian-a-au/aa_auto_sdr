"""Verify the exception hierarchy is shaped as the design spec requires."""

import pytest

from aa_auto_sdr.core import exceptions as exc


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
