"""End-to-end Stripe sandbox lifecycle with real durable SQL, fake test API.

No Stripe keys, network calls, real payment methods or actual WhatsApp
identifiers are required. The signed webhook runs through FastAPI and the
ledger persists across simulated process restarts.
"""

import hashlib
import hmac
import json
import sqlite3
from time import time

import pytest
from fastapi.testclient import TestClient

from app.billing.stripe_test import StripeTestError, StripeTestSettings
from app.billing.test_store import PostgresTestBillingStore, user_hash
from app.handlers.whatsapp import subscription_service
from app.main import app
from app.routers import billing
from app.security import internal_api
from app.subscriptions import Feature, SubscriptionService


USER = "15551234567"
OTHER = "15559876543"
SESSION = "cs_test_sandbox_123"
CUSTOMER = "cus_sandbox_123"
SUBSCRIPTION = "sub_sandbox_123"
PRICE = "price_sandbox_monthly"
WEBHOOK = "/api/v1/billing/test/webhook"
AUTH = {"Authorization": "Bearer test-admin"}


class SQLiteCursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.cursor.close()

    def execute(self, query, params=()):
        self.cursor.execute(
            query.replace("%s", "?").replace("FOR UPDATE", ""),
            params or (),
        )
        return self

    def fetchone(self):
        return self.cursor.fetchone()


class SQLiteConnection:
    def __init__(self, path):
        self.connection = sqlite3.connect(path, timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def cursor(self):
        return SQLiteCursor(self.connection)


class SQLiteHarness:
    def __init__(self, path):
        self.path = str(path)

    def connect(self, _url):
        return SQLiteConnection(self.path)


class FakeStripeTest:
    def __init__(self):
        self.settings = StripeTestSettings(
            secret_key="sk_test_simulated",
            price_id=PRICE,
            webhook_secret="whsec_simulated",
            success_url="https://example.org/checkout/success",
            cancel_url="https://example.org/checkout/cancel",
            portal_return_url="https://example.org/account",
        )
        self.calls = []
        self.checkout = {
            "id": SESSION, "livemode": False, "mode": "subscription",
            "status": "open", "payment_status": "unpaid",
            "client_reference_id": user_hash(USER),
            "customer": None, "subscription": None,
        }
        self.subscription = {
            "id": SUBSCRIPTION, "livemode": False,
            "customer": CUSTOMER, "status": "active",
            "items": {"data": [{"price": {"id": PRICE}}]},
            "latest_invoice": {
                "id": "in_test_123", "livemode": False, "paid": True,
                "status": "paid", "amount_paid": 500, "subscription": SUBSCRIPTION,
            },
        }

    def create_checkout(self, whatsapp_id, **kwargs):
        assert whatsapp_id == USER
        self.calls.append("create_checkout")
        session_id = self.checkout["id"]
        return {
            "session_id": session_id,
            "url": "https://checkout.stripe.com/c/pay/" + session_id,
        }

    def create_portal(self, customer_id):
        self.calls.append("create_portal")
        assert customer_id == CUSTOMER
        return {"url": "https://billing.stripe.com/p/session/test"}

    def get_checkout(self, session_id):
        self.calls.append("get_checkout")
        assert session_id == self.checkout["id"]
        return self.checkout.copy()

    def get_subscription(self, subscription_id):
        self.calls.append("get_subscription")
        assert subscription_id == self.subscription["id"]
        return self.subscription.copy()

    def complete_payment(self):
        self.checkout.update(
            status="complete", payment_status="paid",
            customer=self.subscription["customer"], subscription=self.subscription["id"],
        )


    def next_subscription(self):
        """Emulate a separate verified Stripe TEST Checkout for the same user."""
        self.checkout = {
            "id": "cs_test_sandbox_repeat", "livemode": False,
            "mode": "subscription", "status": "open", "payment_status": "unpaid",
            "client_reference_id": user_hash(USER),
            "customer": None, "subscription": None,
        }
        self.subscription = {
            "id": "sub_sandbox_repeat", "livemode": False,
            "customer": "cus_sandbox_repeat", "status": "active",
            "items": {"data": [{"price": {"id": PRICE}}]},
            "latest_invoice": {
                "id": "in_sandbox_repeat", "livemode": False,
                "paid": True, "status": "paid", "amount_paid": 500,
                "subscription": "sub_sandbox_repeat",
            },
        }


def signed_event(event_id, event_type="checkout.session.completed", object_id=SESSION,
                 extra_object=None):
    obj = {"id": object_id}
    if extra_object:
        obj.update(extra_object)
    body = json.dumps({
        "id": event_id, "livemode": False, "type": event_type,
        "data": {"object": obj},
    }, separators=(",", ":")).encode()
    timestamp = int(time())
    digest = hmac.new(
        b"whsec_simulated", str(timestamp).encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return body, {"Stripe-Signature": f"t={timestamp},v1={digest}"}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    db = SQLiteHarness(tmp_path / "billing.db")
    ledger = PostgresTestBillingStore(
        "postgresql://simulated", connect_fn=db.connect,
    )
    gateway = FakeStripeTest()
    subscription_service.store.clear()
    monkeypatch.setattr(internal_api, "INTERNAL_API_TOKEN", "test-admin")
    monkeypatch.setattr(billing, "STRIPE_TEST_MODE_ENABLED", True)
    monkeypatch.setattr(billing, "STRIPE_TEST_WEBHOOK_SECRET", "whsec_simulated")
    monkeypatch.setattr(billing, "_store", lambda: ledger)
    monkeypatch.setattr(billing, "_gateway", lambda: gateway)
    monkeypatch.setattr(subscription_service, "test_entitlements", ledger)
    yield TestClient(app), ledger, gateway, db
    subscription_service.store.clear()


def send_event(client, event_id, event_type="checkout.session.completed",
               object_id=SESSION, extra_object=None):
    body, headers = signed_event(event_id, event_type, object_id, extra_object)
    return client.post(WEBHOOK, content=body, headers=headers)


def begin_checkout(client):
    response = client.post(
        "/api/v1/billing/test/checkout",
        json={"whatsapp_id": USER}, headers=AUTH,
    )
    assert response.status_code == 200
    assert response.json() == {
        "url": "https://checkout.stripe.com/c/pay/cs_test_sandbox_123"
    }


def test_authenticated_checkout_creates_immutable_binding_without_entitlement(sandbox):
    client, ledger, gateway, db = sandbox
    assert client.post(
        "/api/v1/billing/test/checkout", json={"whatsapp_id": USER},
    ).status_code == 401
    begin_checkout(client)
    assert ledger.find_checkout(SESSION) == (user_hash(USER), None, None)
    assert ledger.has_premium_access(USER) is False
    assert ledger.has_premium_access(OTHER) is False
    assert subscription_service.can_use_feature(USER, Feature.GAS_SEARCH)
    assert not subscription_service.can_use_feature(USER, Feature.PRICE_ALERTS)
    with sqlite3.connect(db.path) as con:
        rows = con.execute("SELECT whatsapp_id_hash FROM stripe_test_checkouts").fetchall()
    assert rows == [(user_hash(USER),)]
    assert USER not in repr(rows)


def test_verified_paid_checkout_grants_only_bound_user_and_survives_restart(sandbox):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    gateway.complete_payment()
    response = send_event(client, "evt_paid_1")
    assert response.status_code == 200
    assert response.json() == {"received": True, "applied": True}
    assert ledger.find_subscription(SUBSCRIPTION) == (SESSION, user_hash(USER), CUSTOMER)
    assert ledger.has_premium_access(USER) is True
    assert not ledger.has_premium_access(OTHER)
    assert subscription_service.can_use_feature(USER, Feature.FAVORITES)
    assert not subscription_service.can_use_feature(OTHER, Feature.FAVORITES)
    assert subscription_service.get_subscription(USER).has_premium_access is False
    reopened = PostgresTestBillingStore(
        "postgresql://simulated", connect_fn=db.connect,
    )
    assert reopened.has_premium_access(USER)
    assert send_event(client, "evt_paid_1").json()["applied"] is False
    assert client.post(
        "/api/v1/billing/test/status",
        json={"whatsapp_id": USER}, headers=AUTH,
    ).json() == {
        "test_mode": True, "linked": True,
        "status": "active", "sandbox_premium_access": True,
    }
    assert client.post(
        "/api/v1/billing/test/portal",
        json={"whatsapp_id": USER}, headers=AUTH,
    ).json()["url"].startswith("https://billing.stripe.com/")


def test_signed_unlinked_or_unpaid_checkout_cannot_grant_premium(sandbox):
    client, ledger, gateway, db = sandbox
    assert send_event(client, "evt_unlinked").json()["applied"] is False
    begin_checkout(client)
    assert send_event(client, "evt_unpaid").json()["applied"] is False
    gateway.complete_payment()
    gateway.checkout["client_reference_id"] = user_hash(OTHER)
    assert send_event(client, "evt_wrong_user").json()["applied"] is False
    assert not ledger.has_premium_access(USER)
    gateway.checkout["client_reference_id"] = user_hash(USER)
    gateway.subscription["items"]["data"][0]["price"]["id"] = "price_other"
    assert send_event(client, "evt_wrong_price").json()["applied"] is True
    assert not ledger.has_premium_access(USER)
    gateway.subscription["items"]["data"][0]["price"]["id"] = PRICE
    assert send_event(client, "evt_correct_price").json()["applied"] is True
    assert ledger.has_premium_access(USER)


def test_out_of_order_invoice_and_failed_payment_revoke_then_renew(sandbox):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    gateway.complete_payment()
    assert send_event(
        client, "evt_early_invoice", "invoice.paid", "in_early",
        {"subscription": SUBSCRIPTION},
    ).json()["applied"] is False
    assert send_event(client, "evt_initial_payment").json()["applied"] is True
    assert ledger.has_premium_access(USER)
    gateway.subscription["status"] = "past_due"
    gateway.subscription["latest_invoice"] = {
        "id": "in_failed", "livemode": False, "paid": False,
        "status": "open", "amount_paid": 0, "subscription": SUBSCRIPTION,
    }
    assert send_event(
        client, "evt_failed", "invoice.payment_failed", "in_failed",
        {"parent": {"subscription_details": {"subscription": SUBSCRIPTION}}},
    ).json()["applied"] is True
    assert not ledger.has_premium_access(USER)
    assert not subscription_service.can_use_feature(USER, Feature.PRICE_ALERTS)
    gateway.subscription["status"] = "active"
    gateway.subscription["latest_invoice"] = {
        "id": "in_renewal", "livemode": False, "paid": True,
        "status": "paid", "amount_paid": 500,
        "subscription": SUBSCRIPTION,
    }
    assert send_event(
        client, "evt_renewal", "invoice.paid", "in_renewal",
        {"subscription": SUBSCRIPTION},
    ).json()["applied"] is True
    assert ledger.has_premium_access(USER)


def test_cancellation_removes_sandbox_access_and_old_events_use_current_state(sandbox):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    gateway.complete_payment()
    assert send_event(client, "evt_start").json()["applied"] is True
    gateway.subscription["status"] = "canceled"
    assert send_event(
        client, "evt_cancel", "customer.subscription.deleted", SUBSCRIPTION,
    ).json()["applied"] is True
    assert not ledger.has_premium_access(USER)
    assert send_event(client, "evt_delayed_invoice").json()["applied"] is True
    assert not ledger.has_premium_access(USER)


def test_existing_checkout_cannot_be_rebound_to_another_user(sandbox):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    from app.billing.test_store import TestBillingStoreError
    with pytest.raises(TestBillingStoreError):
        ledger.save_checkout(SESSION, OTHER)
    gateway.complete_payment()
    assert send_event(client, "evt_authentic").json()["applied"] is True
    assert not ledger.has_premium_access(OTHER)
    assert client.post(
        "/api/v1/billing/test/checkout",
        json={"whatsapp_id": USER}, headers=AUTH,
    ).status_code == 409


def test_disabled_test_mode_does_not_use_sandbox_entitlements(sandbox, monkeypatch):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    gateway.complete_payment()
    assert send_event(client, "evt_active").json()["applied"] is True
    assert ledger.has_premium_access(USER)
    # A real disabled deployment does not inject the TEST ledger.
    disabled = SubscriptionService(subscription_service.store)
    assert not disabled.can_use_feature(USER, Feature.PRICE_ALERTS)
    monkeypatch.setattr(billing, "STRIPE_TEST_MODE_ENABLED", False)
    assert client.post(
        "/api/v1/billing/test/status",
        json={"whatsapp_id": USER}, headers=AUTH,
    ).status_code == 404


def test_tampering_with_signature_cannot_change_bound_paid_status(sandbox):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    gateway.complete_payment()
    body, headers = signed_event("evt_tampered")
    assert client.post(
        WEBHOOK, content=body + b" ", headers=headers,
    ).status_code == 400
    assert not ledger.has_premium_access(USER)
    assert send_event(client, "evt_tampered").json()["applied"] is True


def test_live_subscription_snapshot_never_grants_test_entitlement(sandbox):
    client, ledger, gateway, db = sandbox
    begin_checkout(client)
    gateway.complete_payment()
    gateway.subscription["livemode"] = True
    assert send_event(client, "evt_snapshot_live").status_code == 503
    assert not ledger.has_premium_access(USER)
