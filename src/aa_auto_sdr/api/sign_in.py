"""The sign-in step of `--profile-test`: one token request to Adobe's sign-in service.

`--profile-test` reports two results. This module gives the first one, with a
code that says which part of the credential Adobe rejected. The second result
is the company check, which `AaClient.from_credentials` makes through the SDK.

The token is used only to tell whether sign-in works. It is not kept, and no
value of the credential or the token goes into a message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aa_auto_sdr.core.credentials import MASK, Credentials

IMS_SIGN_IN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
# Seconds to wait for a connection, and then for the answer.
TIMEOUT = (10, 60)
# Adobe's own message is cut to this many characters.
MESSAGE_LIMIT = 200

MESSAGES = {
    "bad_client_id": (
        "Adobe does not know the client ID. Copy the client ID again from the credential in the "
        "Adobe Developer Console."
    ),
    "bad_secret": (
        "Adobe knows the client ID and rejected the secret. Copy the client secret again from the "
        "Adobe Developer Console. A secret that was replaced no longer works."
    ),
    "scopes_rejected": (
        "Adobe rejected one or more scopes. Copy the scopes exactly as the Adobe Developer Console "
        "shows them for this credential."
    ),
    "unreachable": (
        "The tool could not reach Adobe's sign-in service, or the answer did not come from Adobe. "
        "Check the network, the proxy and Adobe's status page, then try again."
    ),
}


@dataclass(frozen=True, slots=True)
class StepResult:
    """One result of the live test. `ok` is None when the step did not run."""

    ok: bool | None
    code: str | None = None
    message: str | None = None
    # True when no answer arrived at all, e.g. the network is down.
    no_answer: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "message": self.message}


NOT_RUN = StepResult(ok=None)


def _post(url: str, data: dict[str, str]) -> Any:
    """The one network call of this module. Tests replace it."""
    import requests

    return requests.post(url, data=data, timeout=TIMEOUT)


def _without_secret(text: str, creds: Credentials) -> str:
    """Adobe's text with any copy of the secret removed, cut to MESSAGE_LIMIT characters."""
    from aa_auto_sdr.core.logging import redact_text

    if creds.secret:
        text = text.replace(creds.secret, MASK)
    return redact_text(text)[:MESSAGE_LIMIT]


def _failed(code: str, *, no_answer: bool = False) -> StepResult:
    return StepResult(ok=False, code=code, message=MESSAGES[code], no_answer=no_answer)


def request_token(creds: Credentials) -> StepResult:
    """Ask Adobe's sign-in service for a token and say how it answered."""
    import requests

    try:
        resp = _post(
            IMS_SIGN_IN_URL,
            {
                "grant_type": "client_credentials",
                "client_id": creds.client_id,
                "client_secret": creds.secret,
                "scope": creds.scopes,
            },
        )
    except requests.RequestException:
        return _failed("unreachable", no_answer=True)
    try:
        body = resp.json()
    except ValueError:
        body = None
    body = body if isinstance(body, dict) else {}
    token = body.get("access_token")
    if resp.status_code == 200 and isinstance(token, str) and token:
        return StepResult(ok=True)
    if resp.status_code == 200:
        # Adobe answers 200 only with a token. Another 200 comes from something
        # between, e.g. a proxy or the sign-in page of a network.
        return _failed("unreachable")
    error = str(body.get("error") or "")
    description = str(body.get("error_description") or "")
    if error == "invalid_client" and "secret" in description:
        return _failed("bad_secret")
    if error == "invalid_client":
        return _failed("bad_client_id")
    if error == "invalid_scope":
        return _failed("scopes_rejected")
    detail = description or (f"error {error}" if error else "no message")
    message = _without_secret(f"Adobe answered HTTP {resp.status_code}: {detail}", creds)
    return StepResult(ok=False, code="sign_in_failed", message=message)
