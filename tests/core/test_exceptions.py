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


@pytest.mark.parametrize(
    ("cls", "raw", "secret", "redacted"),
    [
        (exc.AuthError, "token failed: client_secret=SUPERSECRET123", "SUPERSECRET123", "client_secret=[REDACTED]"),
        (exc.ApiError, "GET /x?access_token=abc.def failed", "abc.def", "access_token=[REDACTED]"),
        (exc.ApiError, "headers Authorization: Bearer abc.def", "abc.def", "Authorization: [REDACTED]"),
    ],
)
def test_str_redacts_secrets(cls: type[Exception], raw: str, secret: str, redacted: str) -> None:
    text = str(cls(raw))
    assert secret not in text
    assert redacted in text


def test_str_without_secrets_is_unchanged() -> None:
    assert str(exc.ConfigError("missing ORG_ID")) == "missing ORG_ID"
    assert str(exc.AmbiguousMatchError("two matches", [("a", "A")])) == "two matches"
