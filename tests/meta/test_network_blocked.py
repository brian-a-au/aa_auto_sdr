"""The autouse guard in tests/conftest.py refuses outbound connections."""

from __future__ import annotations

import socket

import pytest


def test_outbound_connection_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock, pytest.raises(RuntimeError, match="network"):
        sock.connect(("203.0.113.1", 443))


def test_outbound_connect_ex_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock, pytest.raises(RuntimeError, match="network"):
        sock.connect_ex(("203.0.113.1", 443))
