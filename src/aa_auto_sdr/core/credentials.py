"""OAuth Server-to-Server credentials and resolution.

Resolution chain (highest precedence first) is implemented in `resolve()` —
see Task 10.
"""

from __future__ import annotations

from dataclasses import dataclass

from aa_auto_sdr.core.exceptions import ConfigError

_REQUIRED_FIELDS = ("org_id", "client_id", "secret", "scopes")


@dataclass(frozen=True, slots=True)
class Credentials:
    """OAuth S2S credentials plus diagnostic source label."""

    org_id: str
    client_id: str
    secret: str
    scopes: str
    sandbox: str | None
    source: str  # 'profile:<name>' | 'env' | '.env' | 'config.json'

    def validate(self) -> None:
        """Raise ConfigError if any required field is missing or whitespace-only."""
        missing = [f for f in _REQUIRED_FIELDS if not getattr(self, f).strip()]
        if missing:
            raise ConfigError(f"Missing required credential fields: {', '.join(missing)} (loaded from {self.source})")
