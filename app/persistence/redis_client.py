from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Protocol


class RedisClient(Protocol):
    def ping(self) -> bool: ...

    def get(self, name: str) -> str | bytes | None: ...

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> object: ...

    def delete(self, *names: str | bytes) -> int: ...

    def scan_iter(self, match: str) -> Iterable[str | bytes]: ...

    def lock(
        self,
        name: str,
        *,
        timeout: int,
        blocking_timeout: int,
    ) -> AbstractContextManager[object]: ...


def build_redis_client(redis_url: str) -> RedisClient:
    from redis import Redis

    return Redis.from_url(redis_url, decode_responses=True)
