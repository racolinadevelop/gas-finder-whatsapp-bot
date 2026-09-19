import json
import math
import time
from collections.abc import Callable
from hashlib import sha256
from threading import RLock
from typing import Protocol

from app.persistence import RedisClient


class SearchRateLimiter(Protocol):
    def allow(self, user_id: str) -> bool: ...

    def clear(self) -> None: ...


class InMemorySearchRateLimiter:
    """Fixed-window search limiter used for local development and tests."""

    def __init__(
        self,
        *,
        limit: int = 10,
        window_seconds: int = 5 * 60,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")

        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._counters: dict[str, tuple[int, float]] = {}
        self._lock = RLock()

    def allow(self, user_id: str) -> bool:
        now = self._clock()
        key = self._user_hash(user_id)

        with self._lock:
            count, reset_at = self._counters.get(
                key,
                (0, now + self._window_seconds),
            )

            if reset_at <= now:
                count = 0
                reset_at = now + self._window_seconds

            if count >= self._limit:
                return False

            self._counters[key] = (count + 1, reset_at)
            return True

    def clear(self) -> None:
        with self._lock:
            self._counters.clear()

    @staticmethod
    def _user_hash(user_id: str) -> str:
        return sha256(user_id.encode("utf-8")).hexdigest()


class RedisSearchRateLimiter:
    """Search limiter shared by every app instance through Redis."""

    def __init__(
        self,
        client: RedisClient,
        *,
        limit: int = 10,
        window_seconds: int = 5 * 60,
        key_prefix: str = "gas-finder",
        clock: Callable[[], float] = time.time,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")

        self._client = client
        self._limit = limit
        self._window_seconds = window_seconds
        self._key_prefix = key_prefix.rstrip(":")
        self._clock = clock

    def allow(self, user_id: str) -> bool:
        key = self._key(user_id)

        with self._user_lock(user_id):
            now = self._clock()
            count, reset_at = self._read_counter(key)

            if reset_at is None or reset_at <= now:
                count = 0
                reset_at = now + self._window_seconds

            if count >= self._limit:
                return False

            count += 1
            ttl_seconds = max(1, math.ceil(reset_at - now))
            self._client.set(
                key,
                json.dumps(
                    {
                        "count": count,
                        "reset_at": reset_at,
                    },
                    separators=(",", ":"),
                ),
                ex=ttl_seconds,
            )
            return True

    def clear(self) -> None:
        keys = list(
            self._client.scan_iter(
                match=f"{self._key_prefix}:search-rate:*",
            )
        )
        if keys:
            self._client.delete(*keys)

    def _read_counter(self, key: str) -> tuple[int, float | None]:
        raw_value = self._client.get(key)
        if raw_value is None:
            return 0, None
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")

        try:
            data = json.loads(raw_value)
            return int(data["count"]), float(data["reset_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return 0, None

    def _key(self, user_id: str) -> str:
        return (
            f"{self._key_prefix}:search-rate:"
            f"{self._user_hash(user_id)}"
        )

    def _user_lock(self, user_id: str):
        return self._client.lock(
            (
                f"{self._key_prefix}:lock:search-rate:"
                f"{self._user_hash(user_id)}"
            ),
            timeout=10,
            blocking_timeout=5,
        )

    @staticmethod
    def _user_hash(user_id: str) -> str:
        return sha256(user_id.encode("utf-8")).hexdigest()
