from collections.abc import Callable
from dataclasses import dataclass

from app.config import (
    CONVERSATION_TTL_SECONDS,
    DATABASE_URL,
    REDIS_KEY_PREFIX,
    REDIS_URL,
    WHATSAPP_DEDUP_TTL_SECONDS,
)
from app.conversation import (
    InMemoryConversationStore,
    RedisConversationStore,
)
from app.persistence import RedisClient, build_redis_client
from app.subscriptions import (
    InMemorySubscriptionStore,
    PostgresSubscriptionStore,
)
from app.webhooks import (
    InMemoryMessageDeduplicator,
    RedisMessageDeduplicator,
)


@dataclass(frozen=True, slots=True)
class RuntimeState:
    conversation_store: InMemoryConversationStore | RedisConversationStore
    message_deduplicator: (
        InMemoryMessageDeduplicator | RedisMessageDeduplicator
    )
    subscription_store: (
        InMemorySubscriptionStore | PostgresSubscriptionStore
    )
    backend: str
    subscription_backend: str


def build_runtime_state(
    *,
    redis_url: str | None = REDIS_URL,
    redis_client: RedisClient | None = None,
    key_prefix: str = REDIS_KEY_PREFIX,
    conversation_ttl_seconds: int = CONVERSATION_TTL_SECONDS,
    dedup_ttl_seconds: int = WHATSAPP_DEDUP_TTL_SECONDS,
    database_url: str | None = DATABASE_URL,
    postgres_connect_fn: Callable[[str], object] | None = None,
) -> RuntimeState:
    if database_url:
        subscription_store = PostgresSubscriptionStore(
            database_url,
            connect_fn=postgres_connect_fn,
        )
        subscription_backend = "postgres"
    else:
        subscription_store = InMemorySubscriptionStore()
        subscription_backend = "memory"

    if not redis_url:
        return RuntimeState(
            conversation_store=InMemoryConversationStore(),
            message_deduplicator=InMemoryMessageDeduplicator(
                ttl_seconds=dedup_ttl_seconds,
            ),
            subscription_store=subscription_store,
            backend="memory",
            subscription_backend=subscription_backend,
        )

    client = redis_client or build_redis_client(redis_url)
    client.ping()
    return RuntimeState(
        conversation_store=RedisConversationStore(
            client,
            key_prefix=key_prefix,
            ttl_seconds=conversation_ttl_seconds,
        ),
        message_deduplicator=RedisMessageDeduplicator(
            client,
            key_prefix=key_prefix,
            ttl_seconds=dedup_ttl_seconds,
        ),
        subscription_store=subscription_store,
        backend="redis",
        subscription_backend=subscription_backend,
    )
