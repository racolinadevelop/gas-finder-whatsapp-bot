"""Safe, test-only WhatsApp Checkout links bound to verified sender identity."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.billing import whatsapp_test_checkout as checkout
from app.billing.test_store import user_hash


SENDER = "15551234567"
OTHER = "15557654321"
TEST_URL = "https://checkout.stripe.com/c/pay/cs_test_example"


class FakeRedis:
    def __init__(self, *, unavailable=False):
        self.unavailable = unavailable
        self.names = []

    @contextmanager
    def lock(self, name, *, timeout, blocking_timeout):
        if self.unavailable:
            raise ConnectionError("Redis temporarily down")
        self.names.append(name)
        assert timeout >= 30 and blocking_timeout <= 1
        yield


class Store:
    def __init__(self):
        self.checkout_id = None
        self.linked = None
        self.reset_count = 0
        self.saved_favorites = ["Sam's Club"]
        self.saved_language = "es"

    def get_test_subscription(self, sender):
        assert sender == SENDER
        return self.linked

    def find_latest_pending_checkout(self, sender):
        assert sender == SENDER
        return self.checkout_id

    def save_checkout(self, session_id, sender):
        assert sender == SENDER and session_id.startswith("cs_test_")
        self.checkout_id = session_id

    def reset_canceled_user(self, sender, *, customer_id, subscription_id):
        assert sender == SENDER
        assert self.linked == {
            "status": "canceled",
            "customer_id": customer_id,
            "subscription_id": subscription_id,
        }
        self.checkout_id = None
        self.linked = None
        self.reset_count += 1


class Gateway:
    def __init__(self):
        self.create_count = 0
        self.portal_count = 0
        self.checkout_status = "open"
        self.checkout_url = TEST_URL
        self.checkout_reference = user_hash(SENDER)
        self.stripe_subscription_status = "canceled"
        self.stripe_customer = "cus_sandbox"

    def create_checkout(self, sender):
        assert sender == SENDER
        self.create_count += 1
        return {"session_id": "cs_test_example", "url": TEST_URL}

    def get_checkout(self, session):
        assert session == "cs_test_example"
        return {
            "livemode": False, "id": session,
            "client_reference_id": self.checkout_reference,
            "status": self.checkout_status,
            "url": self.checkout_url,
        }

    def get_subscription(self, subscription_id):
        assert subscription_id == "sub_sandbox"
        return {
            "livemode": False, "id": subscription_id,
            "customer": self.stripe_customer,
            "status": self.stripe_subscription_status,
        }

    def create_portal(self, customer_id):
        assert customer_id == "cus_sandbox"
        self.portal_count += 1
        return {"url": "https://billing.stripe.com/p/session/test"}


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setattr(checkout, "STRIPE_TEST_MODE_ENABLED", True)
    monkeypatch.setattr(checkout, "STRIPE_TEST_WHATSAPP_LINKS_ENABLED", True)
    store, gateway, redis = Store(), Gateway(), FakeRedis()
    plan = SimpleNamespace(
        get_subscription=lambda sender: SimpleNamespace(has_premium_access=False)
    )
    return store, gateway, redis, plan


def issue(flow, sender=SENDER):
    store, gateway, redis, plan = flow
    return checkout.create_sender_checkout(
        sender, store=store, gateway=gateway,
        redis_client=redis, subscription_service=plan,
    )


def test_new_sender_gets_bound_link_and_duplicate_taps_reuse_same_checkout(flow):
    store, gateway, redis, plan = flow
    assert issue(flow) == TEST_URL
    assert store.checkout_id == "cs_test_example"
    assert gateway.create_count == 1
    assert issue(flow) == TEST_URL
    assert gateway.create_count == 1
    assert len(redis.names) == 2
    assert all(SENDER not in name and user_hash(SENDER) in name for name in redis.names)
    assert store.saved_favorites == ["Sam's Club"] and store.saved_language == "es"


def test_cancelled_sender_can_repeat_test_only_after_stripe_confirms_cancellation(flow):
    store, gateway, redis, plan = flow
    store.linked = {
        "status": "canceled", "customer_id": "cus_sandbox",
        "subscription_id": "sub_sandbox",
    }
    store.checkout_id = "cs_test_old"
    gateway.stripe_subscription_status = "active"
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="already_linked"):
        issue(flow)
    assert store.reset_count == 0 and gateway.create_count == 0

    gateway.stripe_subscription_status = "canceled"
    assert issue(flow) == TEST_URL
    assert store.reset_count == 1 and gateway.create_count == 1
    assert store.saved_favorites == ["Sam's Club"] and store.saved_language == "es"


@pytest.mark.parametrize("status", ["active", "past_due", "inactive"])
def test_already_linked_subscription_never_creates_second_payment(flow, status):
    store, gateway, redis, plan = flow
    store.linked = {
        "status": status, "customer_id": "cus_sandbox",
        "subscription_id": "sub_sandbox",
    }
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="already_linked"):
        issue(flow)
    assert gateway.create_count == 0


def test_regular_premium_cannot_buy_test_premium_twice(flow):
    store, gateway, redis, plan = flow
    plan.get_subscription = lambda sender: SimpleNamespace(has_premium_access=True)
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="already_premium"):
        issue(flow)
    assert gateway.create_count == 0


@pytest.mark.parametrize("state", ["complete", "unknown"])
def test_previous_checkout_processing_or_unknown_status_blocks_new_link(flow, state):
    store, gateway, redis, plan = flow
    store.checkout_id = "cs_test_example"
    gateway.checkout_status = state
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="processing"):
        issue(flow)
    assert gateway.create_count == 0


def test_expired_checkout_can_be_replaced_but_mismatched_identity_cannot(flow):
    store, gateway, redis, plan = flow
    store.checkout_id = "cs_test_example"
    gateway.checkout_reference = user_hash(OTHER)
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="unavailable"):
        issue(flow)
    gateway.checkout_reference = user_hash(SENDER)
    gateway.checkout_status = "expired"
    assert issue(flow) == TEST_URL
    assert gateway.create_count == 1


@pytest.mark.parametrize("bad_url", [
    "https://evil.example/path", "http://checkout.stripe.com/c/pay/test",
    "https://checkout.stripe.com.evil.com/c/pay/test",
    "https://checkout.stripe.com@evil.com/c/pay/test",
    "https://checkout.stripe.com/",
])
def test_only_stripe_https_checkout_links_are_accepted(flow, bad_url):
    store, gateway, redis, plan = flow
    gateway.create_checkout = lambda _: {
        "session_id": "cs_test_example", "url": bad_url,
    }
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="unavailable"):
        issue(flow)
    assert store.checkout_id is None


def test_redis_failure_and_disabled_flag_fail_closed_without_stripe_call(flow, monkeypatch):
    store, gateway, redis, plan = flow
    redis.unavailable = True
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="unavailable"):
        issue(flow)
    assert gateway.create_count == 0
    monkeypatch.setattr(checkout, "STRIPE_TEST_WHATSAPP_LINKS_ENABLED", False)
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="disabled"):
        issue(flow)
    assert gateway.create_count == 0


def test_test_portal_only_for_linked_active_or_past_due_user(flow):
    store, gateway, redis, plan = flow
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="not_linked"):
        checkout.create_sender_portal(SENDER, store=store, gateway=gateway)
    store.linked = {
        "status": "canceled", "customer_id": "cus_sandbox",
        "subscription_id": "sub_sandbox",
    }
    with pytest.raises(checkout.WhatsAppTestCheckoutError, match="not_linked"):
        checkout.create_sender_portal(SENDER, store=store, gateway=gateway)
    store.linked["status"] = "active"
    assert checkout.create_sender_portal(
        SENDER, store=store, gateway=gateway,
    ) == "https://billing.stripe.com/p/session/test"
    assert gateway.portal_count == 1
