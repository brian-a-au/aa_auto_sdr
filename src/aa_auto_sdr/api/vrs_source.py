"""One successful organization VRS enumeration per explicit invocation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from threading import Lock
from typing import Any

from aa_auto_sdr.api.client import AaClient


class VrsSource:
    """Lazy single-flight source bound to one client and company.

    A failed flight is shared by its waiters, then forgotten so a later suite
    may retry. A successful empty list is a valid retained result.
    """

    def __init__(self, client: AaClient) -> None:
        self._client = client
        self._company_id = client.company_id
        self._lock = Lock()
        self._loaded: list[dict[str, Any]] | None = None
        self._flight: Future[list[dict[str, Any]]] | None = None

    def validate(self, client: AaClient) -> None:
        if client is not self._client or client.company_id != self._company_id:
            raise ValueError("VRS source belongs to a different client or company")

    def get(
        self,
        client: AaClient,
        loader: Callable[[], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        self.validate(client)
        with self._lock:
            if self._loaded is not None:
                return self._loaded
            if self._flight is None:
                flight: Future[list[dict[str, Any]]] = Future()
                self._flight = flight
                owner = True
            else:
                flight = self._flight
                owner = False

        if not owner:
            return flight.result()
        try:
            rows = loader()
        except BaseException as exc:
            with self._lock:
                self._flight = None
                flight.set_exception(exc)
            raise
        with self._lock:
            self._loaded = rows
            self._flight = None
            flight.set_result(rows)
        return rows
