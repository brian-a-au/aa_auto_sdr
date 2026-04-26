"""OAuth Server-to-Server credential dict for aanalytics2."""

from __future__ import annotations

from typing import Any

from aa_auto_sdr.core.credentials import Credentials


def credentials_to_aanalytics2_config(creds: Credentials) -> dict[str, Any]:
    """Map our Credentials shape to aanalytics2's configure() argument."""
    return {
        "org_id": creds.org_id,
        "client_id": creds.client_id,
        "secret": creds.secret,
        "scopes": creds.scopes,
    }
