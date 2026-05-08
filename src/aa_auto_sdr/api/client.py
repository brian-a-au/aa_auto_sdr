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
from aa_auto_sdr.api.resilience import (
    DEFAULT_RETRY_POLICY,
    RetryPolicy,
    classify_transient_sdk_call,
    log_retry_attempt,
    with_retries,
)
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import AuthError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AaClient:
    """Authenticated handle to the AA 2.0 API."""

    handle: Any  # aanalytics2.Analytics
    company_id: str  # globalCompanyId actually used
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY  # v1.7.0 — shared retry budget

    @classmethod
    def from_credentials(
        cls,
        creds: Credentials,
        *,
        company_id: str | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> AaClient:
        """Build an authenticated client.

        If `company_id` is None and the user has access to multiple companies,
        the first is picked deterministically. Pass an explicit `company_id`
        to override (e.g. when the user has multiple AA orgs).

        ``retry_policy`` controls retry-with-jitter for the ``getCompanyId``
        bootstrap call AND is stored on the returned client so downstream
        fetch helpers (api/fetch.py) share the same budget. When ``None``,
        ``DEFAULT_RETRY_POLICY`` is used (max_retries=3, base_delay=0.5s,
        max_delay=10s)."""
        creds.validate()
        config = credentials_to_aanalytics2_config(creds)
        aanalytics2.configure(**config)
        logger.debug(
            "aanalytics2 configured client_id_prefix=%s",
            creds.client_id[:8],
            extra={"client_id_prefix": creds.client_id[:8]},
        )

        policy = retry_policy or DEFAULT_RETRY_POLICY
        login = aanalytics2.Login()
        # Wrap getCompanyId in the same retry pattern as fetchers (per spike
        # D1, aanalytics2 0.5.1's swallowed-stub behavior surfaces transient
        # 5xx as KeyError/ValueError on indexing — `classify_transient_sdk_call`
        # translates those to TransientApiError so `is_retryable` recognizes
        # them and `with_retries` honors --max-retries on the bootstrap path).
        # Auth failures (401/403) bypass urllib3 retry and surface as
        # ConnectionError or AttributeError-style shapes — non-retryable.
        # `log_retry_attempt` threads bootstrap retries into the same
        # `retry_attempt` DEBUG record stream as fetcher retries so operators
        # can grep them under `--log-format json`.
        companies = (
            with_retries(
                lambda: classify_transient_sdk_call(login.getCompanyId),
                policy=policy,
                on_attempt=log_retry_attempt,
            )
            or []
        )
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
        return cls(handle=handle, company_id=chosen, retry_policy=policy)
