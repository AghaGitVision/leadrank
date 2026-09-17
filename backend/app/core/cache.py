"""Cache behind one interface so the scanner never knows whether it is talking
to Redis or to an in-process dict. Production uses Redis (Upstash); the demo
runs with no infrastructure at all."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from ..config import get_settings


class _MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        entry = self._data.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            self._data.pop(key, None)
            return None
        return value

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        self._data[key] = (time.time() + ttl_seconds, value)

    def flushdb(self) -> None:
        self._data.clear()


class ScanCache:
    """Key: scan:{sha256(domain)}. Value: the parsed signal envelope, never raw
    HTML — the payload is ~1KB instead of ~200KB and is directly replayable."""

    def __init__(self) -> None:
        settings = get_settings()
        self.ttl = settings.scan_cache_ttl_days * 86400
        self.backend: Any = _MemoryCache()
        self.kind = "memory"
        if settings.redis_url:
            try:
                import redis  # type: ignore

                self.backend = redis.from_url(settings.redis_url, decode_responses=True)
                self.backend.ping()
                self.kind = "redis"
            except Exception:
                self.backend = _MemoryCache()
                self.kind = "memory"
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(domain: str) -> str:
        return "scan:" + hashlib.sha256(domain.encode()).hexdigest()

    def get(self, domain: str) -> dict | None:
        raw = self.backend.get(self.key(domain))
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def put(self, domain: str, payload: dict) -> None:
        self.backend.setex(self.key(domain), self.ttl, json.dumps(payload))

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total else 0.0


scan_cache = ScanCache()
