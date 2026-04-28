"""Credentials dataclass tests."""

import pytest

from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import ConfigError


def test_credentials_holds_required_fields() -> None:
    c = Credentials(org_id="O", client_id="C", secret="S", scopes="X", source="env")
    assert c.org_id == "O"
    assert c.client_id == "C"
    assert c.secret == "S"
    assert c.scopes == "X"
    assert c.source == "env"


def test_credentials_is_frozen() -> None:
    c = Credentials(org_id="O", client_id="C", secret="S", scopes="X", source="env")
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        c.org_id = "Q"  # type: ignore[misc]


def test_validate_raises_when_required_missing() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Credentials(org_id="", client_id="C", secret="S", scopes="X", source="env").validate()
    assert "org_id" in str(exc_info.value)


def test_validate_passes_when_all_required_present() -> None:
    Credentials(org_id="O", client_id="C", secret="S", scopes="X", source="env").validate()


def test_validate_treats_whitespace_as_empty() -> None:
    with pytest.raises(ConfigError):
        Credentials(org_id="   ", client_id="C", secret="S", scopes="X", source="env").validate()
