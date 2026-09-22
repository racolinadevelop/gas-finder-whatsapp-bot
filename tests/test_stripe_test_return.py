"""Stripe TEST return screen and push receipt must not treat redirects as payment."""

from hashlib import sha256

from fastapi.testclient import TestClient

from app.main import app
from app.routers import billing
from app.billing import whatsapp_receipts as receipts
from app.billing.test_store import user_hash

SENDER = "15551234567"
OTHER = "15559876543"
SESSION = "cs_test_example_123"
EVENT = {
    "id": "evt_test_finished", "livemode": False,
    "type": "checkout.session.completed",
    "data": {"object": {"id": SESSION}},
}


class Redis:
    def __init__(self):
        self.values = {}
        self.calls = []

    def set(self, key, value, *, ex=None, nx=False):
        self.calls.append((key, value, ex, nx))
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)


class Store:
    def __init__(self, *, sender=SENDER, premium=True):
        self.sender, self.premium = sender, premium
        self.lookup_count = 0

    def find_checkout(self, session_id):
        assert session_id == SESSION
        self.lookup_count += 1
        return (user_hash(self.sender), None, None)

    def has_premium_access(self, sender):
        assert sender == SENDER
        return self.premium


def test_return_pages_are_mobile_friendly_and_never_grant_premium(monkeypatch):
    monkeypatch.setattr(billing, "STRIPE_TEST_MODE_ENABLED", True)
    monkeypatch.setattr(
        billing, "send_verified_test_premium_notice",
        lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("Redirect must never notify or provision Premium")
        ),
    )
    client = TestClient(app)
    for kind, text in (
        ("success", "Has terminado el formulario de Stripe TEST."),
        ("cancel", "Inscripción sin completar"),
        ("account", "gestión de tu suscripción de prueba"),
    ):
        response = client.get("/api/v1/billing/test/return/" + kind)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert text in response.text
        assert 'href="whatsapp://"' in response.text
        assert "no-store" in response.headers["cache-control"]
        assert "no-referrer" in response.headers["referrer-policy"]
        assert "<script" not in response.text
        assert SENDER not in response.text and SESSION not in response.text
    assert client.get("/api/v1/billing/test/return/not-a-page").status_code == 404
    monkeypatch.setattr(billing, "STRIPE_TEST_MODE_ENABLED", False)
    assert client.get("/api/v1/billing/test/return/success").status_code == 404


def test_verified_checkout_notifies_only_bound_active_sender_once():
    redis, store, sent = Redis(), Store(), []
    receipts.remember_test_checkout_recipient(
        SENDER, SESSION, redis_client=redis,
    )
    recipient_key, value, ttl, _ = redis.calls[0]
    assert value == SENDER and SENDER not in recipient_key
    assert ttl == receipts.RECIPIENT_TTL_SECONDS
    assert receipts.send_verified_test_premium_notice(
        EVENT, store=store, redis_client=redis,
        send_message=lambda **kw: sent.append(kw),
    )
    assert len(sent) == 1
    assert sent[0]["to"] == SENDER
    assert "Premium de prueba ya está activo" in sent[0]["message"]
    assert not receipts.send_verified_test_premium_notice(
        EVENT, store=store, redis_client=redis,
        send_message=lambda **kw: sent.append(kw),
    )
    assert len(sent) == 1
    assert store.lookup_count == 2


def test_no_notice_for_unpaid_mismatched_recipient_missing_hint_or_noncheckout():
    for sender, premium, existing, event in [
        (SENDER, False, True, EVENT),
        (OTHER, True, True, EVENT),
        (SENDER, True, False, EVENT),
        (SENDER, True, True, {**EVENT, "type": "invoice.paid"}),
        (SENDER, True, True, {**EVENT, "livemode": True}),
    ]:
        redis, store, sent = Redis(), Store(premium=premium), []
        if existing:
            receipts.remember_test_checkout_recipient(
                sender, SESSION, redis_client=redis,
            )
        assert not receipts.send_verified_test_premium_notice(
            event, store=store, redis_client=redis,
            send_message=lambda **kw: sent.append(kw),
        )
        assert sent == []


def test_optional_whatsapp_delivery_failure_never_reverts_paid_entitlement():
    redis, store = Redis(), Store()
    receipts.remember_test_checkout_recipient(
        SENDER, SESSION, redis_client=redis,
    )

    def fail(**_kwargs):
        raise ConnectionError("Meta unavailable")

    assert not receipts.send_verified_test_premium_notice(
        EVENT, store=store, redis_client=redis, send_message=fail,
    )
    assert store.premium is True


def test_receipt_hint_redis_failure_does_not_block_stripe_checkout_or_access():
    class BrokenRedis:
        def set(self, *args, **kwargs):
            raise ConnectionError("temporary Redis failure")

        def get(self, key):
            raise ConnectionError("temporary Redis failure")

    store = Store()
    receipts.remember_test_checkout_recipient(
        SENDER, SESSION, redis_client=BrokenRedis(),
    )
    assert not receipts.send_verified_test_premium_notice(
        EVENT, store=store, redis_client=BrokenRedis(),
    )
    assert store.premium is True
