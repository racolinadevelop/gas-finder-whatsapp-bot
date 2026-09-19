from fnmatch import fnmatch
from threading import RLock

from app.rate_limits import (
    InMemorySearchRateLimiter,
    RedisSearchRateLimiter,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}
        self._lock = RLock()

    def get(self, name: str) -> str | None:
        with self._lock:
            return self.values.get(name)

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        with self._lock:
            if nx and name in self.values:
                return None
            self.values[name] = value
            self.expirations[name] = ex
            return True

    def delete(self, *names: str | bytes) -> int:
        deleted = 0
        with self._lock:
            for name in names:
                if isinstance(name, bytes):
                    name = name.decode("utf-8")
                if name in self.values:
                    deleted += 1
                    self.values.pop(name)
                    self.expirations.pop(name, None)
        return deleted

    def scan_iter(self, match: str):
        with self._lock:
            keys = list(self.values)
        return iter(key for key in keys if fnmatch(key, match))

    def lock(
        self,
        name: str,
        *,
        timeout: int,
        blocking_timeout: int,
    ):
        return self._lock


def test_memory_search_rate_limiter_blocks_after_limit():
    now = [1_000.0]
    limiter = InMemorySearchRateLimiter(
        limit=2,
        window_seconds=60,
        clock=lambda: now[0],
    )

    assert limiter.allow("15551234567") is True
    assert limiter.allow("15551234567") is True
    assert limiter.allow("15551234567") is False

    now[0] += 60

    assert limiter.allow("15551234567") is True


def test_memory_search_rate_limiter_is_per_user():
    limiter = InMemorySearchRateLimiter(
        limit=1,
        window_seconds=60,
    )

    assert limiter.allow("user-a") is True
    assert limiter.allow("user-a") is False
    assert limiter.allow("user-b") is True


def test_redis_search_rate_limiter_is_shared_between_instances():
    client = FakeRedis()
    first = RedisSearchRateLimiter(
        client,
        key_prefix="test",
        limit=2,
        window_seconds=60,
    )
    second = RedisSearchRateLimiter(
        client,
        key_prefix="test",
        limit=2,
        window_seconds=60,
    )

    assert first.allow("15551234567") is True
    assert second.allow("15551234567") is True
    assert first.allow("15551234567") is False
    assert all("15551234567" not in key for key in client.values)


def test_redis_search_rate_limiter_resets_after_window():
    client = FakeRedis()
    now = [1_000.0]
    limiter = RedisSearchRateLimiter(
        client,
        key_prefix="test",
        limit=1,
        window_seconds=60,
        clock=lambda: now[0],
    )

    assert limiter.allow("15551234567") is True
    assert limiter.allow("15551234567") is False

    now[0] += 60

    assert limiter.allow("15551234567") is True


def test_redis_search_rate_limiter_clear():
    client = FakeRedis()
    limiter = RedisSearchRateLimiter(
        client,
        key_prefix="test",
        limit=1,
        window_seconds=60,
    )

    assert limiter.allow("15551234567") is True
    assert limiter.allow("15551234567") is False

    limiter.clear()

    assert limiter.allow("15551234567") is True
