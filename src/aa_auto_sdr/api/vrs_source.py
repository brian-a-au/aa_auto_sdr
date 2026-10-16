"""One successful organization VRS enumeration per explicit invocation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from math import isnan
from threading import Lock
from typing import Any

from aa_auto_sdr.api.client import AaClient


@dataclass
class VrsRows:
    """Retained rows and an optional index over ordinary SDK parent values.

    Unexpected shapes retain the original scan, including its error timing.
    Buckets hold references to rows; consumers still copy selected rows.
    """

    rows: list[dict[str, Any]]
    by_parent: dict[str, list[dict[str, Any]]] | None
    no_parent: int = 0

    @classmethod
    def build(cls, rows: list[dict[str, Any]]) -> VrsRows:
        by_parent: dict[str, list[dict[str, Any]]] = {}
        no_parent = 0
        for row in rows:
            if type(row) is not dict:
                return cls(rows, None)
            parent = row.get("parentRsid")
            if type(parent) is str:
                by_parent.setdefault(parent, []).append(row)
                no_parent += not parent
            elif parent is None or (type(parent) is float and isnan(parent)):
                no_parent += 1
            else:
                return cls(rows, None)
        return cls(rows, by_parent, no_parent)


class VrsSource:
    """Lazy single-flight source bound to one client and company.

    A failed flight is shared by its waiters, then forgotten so a later suite
    may retry. A successful empty list is a valid retained result.
    """

    def __init__(self, client: AaClient) -> None:
        self._client = client
        self._company_id = client.company_id
        self._lock = Lock()
        self._loaded: VrsRows | None = None
        self._flight: Future[VrsRows] | None = None

    def validate(self, client: AaClient) -> None:
        if client is not self._client or client.company_id != self._company_id:
            raise ValueError("VRS source belongs to a different client or company")

    def get(
        self,
        client: AaClient,
        loader: Callable[[], list[dict[str, Any]]],
    ) -> VrsRows:
        self.validate(client)
        with self._lock:
            if self._loaded is not None:
                return self._loaded
            if self._flight is None:
                flight: Future[VrsRows] = Future()
                self._flight = flight
                owner = True
            else:
                flight = self._flight
                owner = False

        if not owner:
            return flight.result()
        try:
            rows = VrsRows.build(loader())
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
