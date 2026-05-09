"""ValidationCache — see spec §3.3."""

from __future__ import annotations

import logging
import threading
import time

import pytest

from aa_auto_sdr.api.cache import ValidationCache


def test_init_validates_max_size() -> None:
    with pytest.raises(ValueError, match="max_size must be >= 1"):
        ValidationCache(max_size=0)


def test_init_validates_ttl_seconds() -> None:
    with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
        ValidationCache(ttl_seconds=0)


def test_get_returns_none_on_miss() -> None:
    cache = ValidationCache()
    assert cache.get("absent") is None
    assert cache.stats()["misses"] == 1
    assert cache.stats()["hits"] == 0


def test_put_then_get_round_trip() -> None:
    cache = ValidationCache()
    cache.put("k1", {"v": 1})
    assert cache.get("k1") == {"v": 1}
    assert cache.stats()["hits"] == 1
    assert cache.stats()["misses"] == 0


def test_lru_eviction_at_max_size() -> None:
    cache = ValidationCache(max_size=2)
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.put("k3", "v3")  # evicts k1
    assert cache.get("k1") is None
    assert cache.get("k2") == "v2"
    assert cache.get("k3") == "v3"
    assert cache.stats()["evictions"] == 1


def test_lru_bump_on_get_protects_recently_used() -> None:
    cache = ValidationCache(max_size=2)
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.get("k1")  # bump k1 to MRU
    cache.put("k3", "v3")  # evicts k2 (LRU), not k1
    assert cache.get("k1") == "v1"
    assert cache.get("k2") is None
    assert cache.get("k3") == "v3"


def test_ttl_expiration() -> None:
    cache = ValidationCache(ttl_seconds=1)
    cache.put("k1", "v1")
    assert cache.get("k1") == "v1"
    time.sleep(1.01)
    assert cache.get("k1") is None
    assert cache.stats()["expires"] == 1


def test_clear_resets_all_entries() -> None:
    cache = ValidationCache()
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.clear()
    assert cache.get("k1") is None
    assert cache.get("k2") is None
    assert cache.stats()["size"] == 0


def test_stats_size_reflects_current_entries() -> None:
    cache = ValidationCache()
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    assert cache.stats()["size"] == 2


def test_thread_safety_concurrent_get_put() -> None:
    """4 threads, 250 ops each. No exceptions; final stats consistent."""
    cache = ValidationCache(max_size=100)

    def worker(thread_id: int) -> None:
        for i in range(250):
            key = f"t{thread_id}-k{i % 50}"  # 50 keys reused -> some overwrites
            cache.put(key, i)
            cache.get(key)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stats = cache.stats()
    # 4 threads × 250 puts + 4 × 250 gets = 1000 puts + 1000 gets.
    # Get count is hits + misses; both depend on schedule, but their sum is exactly 1000.
    assert stats["hits"] + stats["misses"] == 1000
    assert stats["size"] <= 100  # max_size bound respected


def test_get_emits_hit_log_record(caplog: pytest.LogCaptureFixture) -> None:
    cache = ValidationCache()
    cache.put("k1", "v1")
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.cache"):
        cache.get("k1")
    hit_records = [r for r in caplog.records if getattr(r, "cache_event", None) == "hit"]
    assert len(hit_records) == 1


def test_get_emits_miss_log_record(caplog: pytest.LogCaptureFixture) -> None:
    cache = ValidationCache()
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.cache"):
        cache.get("absent")
    miss_records = [r for r in caplog.records if getattr(r, "cache_event", None) == "miss"]
    assert len(miss_records) == 1


def test_put_emits_evict_log_record_on_overflow(caplog: pytest.LogCaptureFixture) -> None:
    cache = ValidationCache(max_size=1)
    cache.put("k1", "v1")
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.cache"):
        cache.put("k2", "v2")  # evicts k1
    evict_records = [r for r in caplog.records if getattr(r, "cache_event", None) == "evict"]
    assert len(evict_records) == 1


def test_get_emits_expire_log_record(caplog: pytest.LogCaptureFixture) -> None:
    cache = ValidationCache(ttl_seconds=1)
    cache.put("k1", "v1")
    time.sleep(1.01)
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.cache"):
        cache.get("k1")
    expire_records = [r for r in caplog.records if getattr(r, "cache_event", None) == "expire"]
    assert len(expire_records) == 1
