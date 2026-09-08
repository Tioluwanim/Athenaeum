"""
app/utils/cache.py — Lightweight in-process TTL cache.

Deliberately not Redis: a single library ICT-section deployment (one
FastAPI process, 10-15 concurrent users) doesn't need a distributed cache,
and adding Redis as a hard dependency would work against the "runs on a
LAN box with unreliable internet" deployment option. The interface below
is the seam — swap `TTLCache` for a Redis-backed implementation later
without touching call sites, if this ever needs to run multi-process.
"""
from __future__ import annotations

import hashlib
import time
from functools import wraps
from threading import Lock
from typing import Any, Callable


class TTLCache:
    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 2048) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._store) >= self.max_entries:
                # Evict the oldest ~10% rather than a full flush.
                oldest = sorted(self._store.items(), key=lambda kv: kv[1][0])[: max(1, self.max_entries // 10)]
                for k, _ in oldest:
                    self._store.pop(k, None)
            self._store[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


def make_key(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cached(cache: TTLCache, key_fn: Callable[..., str]):
    """Decorator for sync functions. Async call-sites should call
    cache.get/set directly (see rag_graph.py) since a decorator can't
    cleanly wrap both sync and async without duplicating logic."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = key_fn(*args, **kwargs)
            hit = cache.get(key)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result
        return wrapper
    return decorator


# Shared caches used across services
retrieval_cache = TTLCache(ttl_seconds=180.0)   # hybrid_search results
embedding_cache = TTLCache(ttl_seconds=3600.0)  # query embeddings rarely change meaning
