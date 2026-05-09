"""Thread-safe LRU cache with TTL semantics.

Mirrors cja_auto_sdr/api/cache.py::ValidationCache. Skips cja's
SharedValidationCache (Manager-backed) — aa uses ThreadPoolExecutor;
threads share memory natively; no Manager needed.

Cache target deliberately empty in v1.8.0. The class ships now to lock
the API + flag surface; v1.12.0's quality engine will be the first
caller to populate entries. See docs/superpowers/specs/2026-05-09-aa-auto-sdr-v1.8.0-design.md §3.3.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)


class ValidationCache:
    """Thread-safe LRU cache with TTL eviction.

    API:
      cache.get(key) -> value | None      # None on miss or expired
      cache.put(key, value) -> None       # may evict LRU entry to fit max_size
      cache.clear() -> None               # remove all entries
      cache.stats() -> dict               # {hits, misses, evictions, expires, size}

    Thread safety: single threading.Lock around all mutations and reads.
    Lock is fine-grained per operation; no long-held locks.

    Usage:
      cache = ValidationCache(max_size=1000, ttl_seconds=3600)
      if (result := cache.get(key)) is None:
          result = expensive_validation(...)
          cache.put(key, result)
      return result
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,
    ) -> None:
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expires": 0}

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                logger.debug(
                    "cache_event=miss key=%s",
                    key,
                    extra={"cache_event": "miss"},
                )
                return None
            value, ts = entry
            if time.monotonic() - ts > self.ttl_seconds:
                del self._cache[key]
                self._stats["expires"] += 1
                logger.debug(
                    "cache_event=expire key=%s",
                    key,
                    extra={"cache_event": "expire"},
                )
                return None
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            logger.debug(
                "cache_event=hit key=%s",
                key,
                extra={"cache_event": "hit"},
            )
            return value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, time.monotonic())
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1
                logger.debug(
                    "cache_event=evict",
                    extra={"cache_event": "evict"},
                )

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {**self._stats, "size": len(self._cache)}
