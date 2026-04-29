"""Wrapper around aanalytics2.Analytics.

This is the **only** module (besides api/auth.py and api/fetch.py) that
imports aanalytics2. SDK isolation is enforced by a meta-test in v0.9.

API 2.0 only. No 1.4 fallback paths exist or will be added here.

Bootstrap order (validated by spike — see docs/superpowers/spikes/...):
  1. aanalytics2.configure(**creds)
  2. login = aanalytics2.Login()                  # read-only helper
  3. companies = login.getCompanyId()             # returns [{globalCompanyId, ...}]
  4. handle = aanalytics2.Analytics(globalCompanyId)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aanalytics2  # type: ignore[import-untyped]

from aa_auto_sdr.api.auth import credentials_to_aanalytics2_config
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import AuthError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AaClient:
    """Authenticated handle to the AA 2.0 API."""

    handle: Any  # aanalytics2.Analytics
    company_id: str  # globalCompanyId actually used

    @classmethod
    def from_credentials(
        cls,
        creds: Credentials,
        *,
        company_id: str | None = None,
    ) -> AaClient:
        """Build an authenticated client.

        If `company_id` is None and the user has access to multiple companies,
        the first is picked deterministically. Pass an explicit `company_id`
        to override (e.g. when the user has multiple AA orgs)."""
        creds.validate()
        config = credentials_to_aanalytics2_config(creds)
        aanalytics2.configure(**config)
        logger.debug(
            "aanalytics2 configured client_id_prefix=%s",
            creds.client_id[:8],
            extra={"client_id_prefix": creds.client_id[:8]},
        )

        login = aanalytics2.Login()
        companies = login.getCompanyId() or []
        logger.debug(
            "getCompanyId returned count=%s",
            len(companies),
            extra={"count": len(companies)},
        )
        if not companies:
            logger.error(
                "auth_failure reason=no_companies",
                extra={"error_class": "AuthError", "reason": "no_companies"},
            )
            raise AuthError(
                "No companies visible to these credentials. Verify the integration "
                "is added to an Adobe Analytics Product Profile in Admin Console.",
            )

        chosen = company_id or companies[0].get("globalCompanyId")
        if not chosen:
            logger.error(
                "auth_failure reason=missing_global_company_id",
                extra={"error_class": "AuthError", "reason": "missing_global_company_id"},
            )
            raise AuthError("getCompanyId() returned a record with no globalCompanyId field")

        handle = aanalytics2.Analytics(chosen)
        logger.info(
            "auth bootstrap ok company_id=%s source=%s",
            chosen,
            "explicit" if company_id else "first_of_n",
            extra={
                "company_id": chosen,
                "company_id_source": "explicit" if company_id else "first_of_n",
            },
        )
        return cls(handle=handle, company_id=chosen)
