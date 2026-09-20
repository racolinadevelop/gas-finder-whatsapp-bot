"""Durable TEST-only Checkout identity binding and entitlement ledger.

Only SHA-256 user identifiers are persisted. This ledger never updates the
live/general user_subscriptions table, so disabling test billing instantly
revokes sandbox-only feature access.
"""

from hashlib import sha256
from typing import Callable


class TestBillingStoreError(Exception):
    """A test Checkout does not belong to this user or cannot be reconciled."""


def user_hash(whatsapp_id: str) -> str:
    return sha256(whatsapp_id.encode("utf-8")).hexdigest()


class PostgresTestBillingStore:
    def __init__(self, database_url: str, *, connect_fn: Callable | None = None):
        if not database_url:
            raise ValueError("PostgreSQL URL is required for test billing")
        self._database_url = database_url
        self._connect_fn = connect_fn
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stripe_test_checkouts (
                        checkout_session_id TEXT PRIMARY KEY,
                        whatsapp_id_hash TEXT NOT NULL,
                        customer_id TEXT,
                        subscription_id TEXT UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stripe_test_entitlements (
                        whatsapp_id_hash TEXT PRIMARY KEY,
                        customer_id TEXT NOT NULL,
                        subscription_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stripe_test_processed_events (
                        event_id TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def _connect(self):
        if self._connect_fn is not None:
            return self._connect_fn(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url)

    def save_checkout(self, session_id: str, whatsapp_id: str) -> None:
        if not session_id.startswith("cs_test_"):
            raise TestBillingStoreError("Only test Checkout sessions can be bound")
        hashed = user_hash(whatsapp_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stripe_test_checkouts (
                        checkout_session_id, whatsapp_id_hash
                    ) VALUES (%s, %s)
                    ON CONFLICT (checkout_session_id) DO NOTHING
                    """,
                    (session_id, hashed),
                )
                cur.execute(
                    """
                    SELECT whatsapp_id_hash FROM stripe_test_checkouts
                    WHERE checkout_session_id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if row is None or row[0] != hashed:
                    raise TestBillingStoreError("Checkout session already belongs to another user")

    def find_checkout(self, session_id: str) -> tuple[str, str | None, str | None] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT whatsapp_id_hash, customer_id, subscription_id
                    FROM stripe_test_checkouts WHERE checkout_session_id = %s
                    """,
                    (session_id,),
                )
                return cur.fetchone()

    def find_subscription(self, subscription_id: str) -> tuple[str, str, str] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT checkout_session_id, whatsapp_id_hash, customer_id
                    FROM stripe_test_checkouts WHERE subscription_id = %s
                    """,
                    (subscription_id,),
                )
                return cur.fetchone()

    def get_test_subscription(self, whatsapp_id: str) -> dict | None:
        """Read test-only status for an authenticated admin or feature gate."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT customer_id, subscription_id, status
                    FROM stripe_test_entitlements
                    WHERE whatsapp_id_hash = %s
                    """,
                    (user_hash(whatsapp_id),),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "customer_id": row[0],
            "subscription_id": row[1],
            "status": row[2],
        }

    def has_premium_access(self, whatsapp_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status FROM stripe_test_entitlements
                    WHERE whatsapp_id_hash = %s
                    """,
                    (user_hash(whatsapp_id),),
                )
                row = cur.fetchone()
        return row is not None and row[0] == "active"

    def apply_verified_state(
        self,
        *,
        event_id: str,
        session_id: str,
        customer_id: str,
        subscription_id: str,
        status: str,
    ) -> bool:
        """Persist only after Stripe has been re-queried and verified.

        The receipt and entitlement update commit in the same transaction.
        Stripe retries if any SQL operation raises and the transaction aborts.
        Duplicate event IDs cannot apply twice. The checkout association is
        immutable and cannot link a different customer or subscription.
        """
        if (
            not event_id.startswith("evt_")
            or not session_id.startswith("cs_test_")
            or not customer_id.startswith("cus_")
            or not subscription_id.startswith("sub_")
            or status not in {"active", "past_due", "canceled", "inactive"}
        ):
            raise TestBillingStoreError("Invalid test billing state")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT whatsapp_id_hash, customer_id, subscription_id
                    FROM stripe_test_checkouts
                    WHERE checkout_session_id = %s
                    FOR UPDATE
                    """,
                    (session_id,),
                )
                record = cur.fetchone()
                if record is None:
                    raise TestBillingStoreError("Unknown Checkout session")
                hashed, existing_customer, existing_subscription = record
                if (
                    existing_customer is not None and existing_customer != customer_id
                ) or (
                    existing_subscription is not None
                    and existing_subscription != subscription_id
                ):
                    raise TestBillingStoreError("Checkout billing identity changed")
                cur.execute(
                    """
                    SELECT customer_id, subscription_id
                    FROM stripe_test_entitlements
                    WHERE whatsapp_id_hash = %s
                    FOR UPDATE
                    """,
                    (hashed,),
                )
                existing = cur.fetchone()
                if existing is not None and existing != (
                    customer_id, subscription_id
                ):
                    raise TestBillingStoreError("Another subscription already belongs to user")

                cur.execute(
                    """
                    INSERT INTO stripe_test_processed_events (event_id)
                    VALUES (%s)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    (event_id,),
                )
                if cur.fetchone() is None:
                    return False
                cur.execute(
                    """
                    UPDATE stripe_test_checkouts
                    SET customer_id = %s, subscription_id = %s
                    WHERE checkout_session_id = %s
                    """,
                    (customer_id, subscription_id, session_id),
                )
                cur.execute(
                    """
                    INSERT INTO stripe_test_entitlements (
                        whatsapp_id_hash, customer_id, subscription_id, status
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (whatsapp_id_hash) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (hashed, customer_id, subscription_id, status),
                )
        return True

    def reset_canceled_user(
        self,
        whatsapp_id: str,
        *,
        customer_id: str,
        subscription_id: str,
    ) -> bool:
        """Forget a verified canceled TEST linkage so an admin can test again.

        Only sandbox Checkout and entitlement rows are deleted. This never
        touches language preferences, favorites, normal plans or event receipts.
        The locked row + expected IDs prevent racing a new active subscription.
        Subsequent events for forgotten old sessions are ignored as unbound.
        """
        hashed = user_hash(whatsapp_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT customer_id, subscription_id, status
                    FROM stripe_test_entitlements
                    WHERE whatsapp_id_hash = %s
                    FOR UPDATE
                    """,
                    (hashed,),
                )
                row = cur.fetchone()
                if row != (customer_id, subscription_id, "canceled"):
                    raise TestBillingStoreError(
                        "Test subscription changed or is not canceled"
                    )
                cur.execute(
                    """
                    DELETE FROM stripe_test_checkouts
                    WHERE whatsapp_id_hash = %s
                    """,
                    (hashed,),
                )
                cur.execute(
                    """
                    DELETE FROM stripe_test_entitlements
                    WHERE whatsapp_id_hash = %s
                    AND customer_id = %s
                    AND subscription_id = %s
                    AND status = 'canceled'
                    """,
                    (hashed, customer_id, subscription_id),
                )
        return True
