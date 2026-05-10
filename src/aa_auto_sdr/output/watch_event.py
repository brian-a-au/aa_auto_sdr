"""Watch-mode NDJSON event emitter.

Owns the `aa-watch-event/v1` schema string. Emits one JSON object per line
to a stream (default sys.stdout), flushed after each emit so pipe consumers
see events in real time.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Protocol, TextIO

WATCH_EVENT_SCHEMA = "aa-watch-event/v1"


class WatchEventEmitter(Protocol):
    def emit(self, payload: dict[str, Any]) -> None: ...


class StdoutEmitter:
    """Default emitter: writes NDJSON to stdout, flushes after every emit."""

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def emit(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise TypeError(f"emit() requires a dict payload, got {type(payload).__name__}")
        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        self._stream.write(line)
        self._stream.write("\n")
        self._stream.flush()
