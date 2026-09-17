from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from threading import RLock
from typing import Protocol

from app.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionStatus,
    UserSubscription,
)


class SubscriptionStore(Protocol):
    def get(self, whatsapp_id: str) -> UserSubscription | None: ...

    def get_or_create(self, whatsapp_id: str) -> UserSubscription: ...

    def update(self, whatsapp_id: str, **changes) -> UserSubscription: ...


class InMemorySubscriptionStore:
    """Temporary subscription storage for local development and tests."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, UserSubscription] = {}
        self._lock = RLock()

    def get(self, whatsapp_id: str) -> UserSubscription | None:
        with self._lock:
            return self._subscriptions.get(whatsapp_id)

    def get_or_create(self, whatsapp_id: str) -> UserSubscription:
        with self._lock:
            subscription = self._subscriptions.get(whatsapp_id)

            if subscription is None:
                subscription = UserSubscription(whatsapp_id=whatsapp_id)
                self._subscriptions[whatsapp_id] = subscription

            return subscription

    def update(self, whatsapp_id: str, **changes) -> UserSubscription:
        with self._lock:
            subscription = self.get_or_create(whatsapp_id)
            updated = replace(subscription, **changes)
            self._subscriptions[whatsapp_id] = updated
            return updated

    def clear(self) -> None:
        with self._lock:
            self._subscriptions.clear()


class PostgresSubscriptionStore:
    """Persistent subscription storage backed by PostgreSQL."""

    def __init__(
        self,
        database_url: str,
        *,
        connect_fn: Callable[[str], object] | None = None,
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")

        self._database_url = database_url
        self._connect_fn = connect_fn
        self._ensure_schema()

    def get(self, whatsapp_id: str) -> UserSubscription | None:
        whatsapp_id_hash = self._hash_whatsapp_id(whatsapp_id)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        plan,
                        status,
                        billing_customer_id,
                        billing_subscription_id
                    FROM user_subscriptions
                    WHERE whatsapp_id_hash = %s
                    """,
                    (whatsapp_id_hash,),
                )
                row = cursor.fetchone()

        if row is None:
            return None

        return UserSubscription(
            whatsapp_id=whatsapp_id,
            plan=SubscriptionPlan(row[0]),
            status=SubscriptionStatus(row[1]),
            billing_customer_id=row[2],
            billing_subscription_id=row[3],
        )

    def get_or_create(self, whatsapp_id: str) -> UserSubscription:
        whatsapp_id_hash = self._hash_whatsapp_id(whatsapp_id)
        default = UserSubscription(whatsapp_id=whatsapp_id)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_subscriptions (
                        whatsapp_id_hash,
                        plan,
                        status,
                        billing_customer_id,
                        billing_subscription_id
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (whatsapp_id_hash) DO NOTHING
                    """,
                    (
                        whatsapp_id_hash,
                        default.plan.value,
                        default.status.value,
                        default.billing_customer_id,
                        default.billing_subscription_id,
                    ),
                )
                cursor.execute(
                    """
                    SELECT
                        plan,
                        status,
                        billing_customer_id,
                        billing_subscription_id
                    FROM user_subscriptions
                    WHERE whatsapp_id_hash = %s
                    """,
                    (whatsapp_id_hash,),
                )
                row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Could not create or load subscription")

        return UserSubscription(
            whatsapp_id=whatsapp_id,
            plan=SubscriptionPlan(row[0]),
            status=SubscriptionStatus(row[1]),
            billing_customer_id=row[2],
            billing_subscription_id=row[3],
        )

    def update(self, whatsapp_id: str, **changes) -> UserSubscription:
        current = self.get_or_create(whatsapp_id)
        updated = replace(current, **changes)
        whatsapp_id_hash = self._hash_whatsapp_id(whatsapp_id)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_subscriptions (
                        whatsapp_id_hash,
                        plan,
                        status,
                        billing_customer_id,
                        billing_subscription_id
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (whatsapp_id_hash) DO UPDATE SET
                        plan = EXCLUDED.plan,
                        status = EXCLUDED.status,
                        billing_customer_id = EXCLUDED.billing_customer_id,
                        billing_subscription_id = EXCLUDED.billing_subscription_id,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        whatsapp_id_hash,
                        updated.plan.value,
                        updated.status.value,
                        updated.billing_customer_id,
                        updated.billing_subscription_id,
                    ),
                )

        return updated

    def clear(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM user_subscriptions")

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        whatsapp_id_hash TEXT PRIMARY KEY,
                        plan TEXT NOT NULL,
                        status TEXT NOT NULL,
                        billing_customer_id TEXT,
                        billing_subscription_id TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                            DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ NOT NULL
                            DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._database_url)

        import psycopg

        return psycopg.connect(self._database_url)

    @staticmethod
    def _hash_whatsapp_id(whatsapp_id: str) -> str:
        return sha256(whatsapp_id.encode("utf-8")).hexdigest()
