from app.runtime import build_runtime_state
from app.subscriptions import (
    PostgresSubscriptionStore,
    SubscriptionPlan,
    SubscriptionService,
    SubscriptionStatus,
)


class FakePostgres:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, str | None]] = {}
        self.schema_created = False
        self.connect_count = 0

    def connect(self, _database_url: str):
        self.connect_count += 1
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database: FakePostgres) -> None:
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor(self.database)


class FakeCursor:
    def __init__(self, database: FakePostgres) -> None:
        self.database = database
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.split()).lower()

        if normalized.startswith("create table"):
            self.database.schema_created = True
            self._row = None
            return

        if normalized.startswith("select"):
            key = params[0]
            record = self.database.rows.get(key)
            self._row = (
                None
                if record is None
                else (
                    record["plan"],
                    record["status"],
                    record["billing_customer_id"],
                    record["billing_subscription_id"],
                )
            )
            return

        if normalized.startswith("insert into user_subscriptions"):
            (
                key,
                plan,
                status,
                billing_customer_id,
                billing_subscription_id,
            ) = params
            record = {
                "plan": plan,
                "status": status,
                "billing_customer_id": billing_customer_id,
                "billing_subscription_id": billing_subscription_id,
            }

            if "do nothing" in normalized:
                self.database.rows.setdefault(key, record)
            else:
                self.database.rows[key] = record

            self._row = None
            return

        if normalized.startswith("delete from user_subscriptions"):
            self.database.rows.clear()
            self._row = None
            return

        raise AssertionError(f"Unexpected SQL in fake database: {query}")

    def fetchone(self):
        return self._row


def test_postgres_subscription_survives_store_recreation():
    database = FakePostgres()
    first_store = PostgresSubscriptionStore(
        "postgresql://example",
        connect_fn=database.connect,
    )
    first_service = SubscriptionService(first_store)

    expected = first_service.activate_premium(
        "15551234567",
        billing_customer_id="cus_test",
        billing_subscription_id="sub_test",
    )

    second_store = PostgresSubscriptionStore(
        "postgresql://example",
        connect_fn=database.connect,
    )
    loaded = second_store.get("15551234567")

    assert database.schema_created is True
    assert loaded == expected
    assert loaded.plan == SubscriptionPlan.PREMIUM
    assert loaded.status == SubscriptionStatus.ACTIVE


def test_postgres_store_hashes_whatsapp_identifier():
    database = FakePostgres()
    store = PostgresSubscriptionStore(
        "postgresql://example",
        connect_fn=database.connect,
    )

    store.get_or_create("15551234567")

    assert len(database.rows) == 1
    stored_key = next(iter(database.rows))
    assert stored_key != "15551234567"
    assert "15551234567" not in stored_key
    assert len(stored_key) == 64


def test_runtime_uses_postgres_for_subscriptions_when_configured():
    database = FakePostgres()

    state = build_runtime_state(
        redis_url=None,
        database_url="postgresql://example",
        postgres_connect_fn=database.connect,
    )

    assert state.backend == "memory"
    assert state.subscription_backend == "postgres"
    assert isinstance(
        state.subscription_store,
        PostgresSubscriptionStore,
    )
    assert database.schema_created is True


def test_runtime_uses_memory_for_subscriptions_without_database_url():
    state = build_runtime_state(
        redis_url=None,
        database_url=None,
    )

    assert state.subscription_backend == "memory"
