from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatch
from threading import Barrier, RLock

from app.conversation import (
    ConversationSession,
    ConversationState,
    InMemoryConversationStore,
    RedisConversationStore,
)
from app.runtime import build_runtime_state
from app.webhooks import (
    InMemoryMessageDeduplicator,
    RedisMessageDeduplicator,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}
        self.ping_count = 0
        self.lock_names: list[str] = []
        self._lock = RLock()

    def ping(self) -> bool:
        self.ping_count += 1
        return True

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
        self.lock_names.append(name)
        return self._lock


def test_redis_conversation_store_survives_store_recreation():
    client = FakeRedis()
    first_store = RedisConversationStore(
        client,
        key_prefix="test",
        ttl_seconds=120,
    )

    updated = first_store.update(
        "15551234567",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="diesel",
        sort="cheapest",
        max_distance_miles=10.0,
    )
    second_store = RedisConversationStore(
        client,
        key_prefix="test",
        ttl_seconds=120,
    )

    assert second_store.get("15551234567") == updated
    assert updated == ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="diesel",
        sort="cheapest",
        max_distance_miles=10.0,
    )
    assert set(client.expirations.values()) == {120}
    assert all("15551234567" not in key for key in client.values)
    assert client.lock_names


def test_redis_conversation_store_pop_and_clear():
    client = FakeRedis()
    store = RedisConversationStore(client, key_prefix="test")
    first = store.get_or_create("first")
    store.get_or_create("second")

    assert store.pop("first") == first
    assert store.get("first") is None

    store.clear()

    assert store.get("second") is None


def test_redis_deduplicator_is_shared_between_instances():
    client = FakeRedis()
    first = RedisMessageDeduplicator(
        client,
        key_prefix="test",
        ttl_seconds=60,
    )
    second = RedisMessageDeduplicator(
        client,
        key_prefix="test",
        ttl_seconds=60,
    )

    assert first.claim("wamid.shared") is True
    assert second.claim("wamid.shared") is False
    assert len(first) == 1
    assert set(client.expirations.values()) == {60}
    assert all("wamid.shared" not in key for key in client.values)

    second.release("wamid.shared")

    assert first.claim("wamid.shared") is True


def test_redis_deduplicator_allows_one_concurrent_claim():
    client = FakeRedis()
    deduplicators = [
        RedisMessageDeduplicator(client, key_prefix="test")
        for _ in range(8)
    ]
    barrier = Barrier(len(deduplicators))

    def claim(deduplicator: RedisMessageDeduplicator) -> bool:
        barrier.wait()
        return deduplicator.claim("wamid.concurrent-shared")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(claim, deduplicators))

    assert results.count(True) == 1
    assert results.count(False) == 7


def test_runtime_uses_memory_without_redis_url():
    state = build_runtime_state(redis_url=None)

    assert state.backend == "memory"
    assert isinstance(state.conversation_store, InMemoryConversationStore)
    assert isinstance(
        state.message_deduplicator,
        InMemoryMessageDeduplicator,
    )


def test_runtime_uses_and_checks_redis_when_configured():
    client = FakeRedis()

    state = build_runtime_state(
        redis_url="redis://example",
        redis_client=client,
        key_prefix="test",
        conversation_ttl_seconds=120,
        dedup_ttl_seconds=60,
    )

    assert state.backend == "redis"
    assert isinstance(state.conversation_store, RedisConversationStore)
    assert isinstance(state.message_deduplicator, RedisMessageDeduplicator)
    assert client.ping_count == 1
