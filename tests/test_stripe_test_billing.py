"""Stripe test mode only: verify security, HTTP isolation and no plan changes."""

import hashlib
import hmac
import json
from time import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.billing import (
    StripeTestError,
    StripeTestGateway,
    StripeTestSettings,
    verify_test_webhook,
)
from app.main import app
from app.routers import billing
from app.security import internal_api
from app.handlers.whatsapp import subscription_service


def settings():
    return StripeTestSettings(
        secret_key="sk_test_test_only",
        price_id="price_test_subscription",
        webhook_secret="whsec_test_only",
        success_url="https://example.org/checkout/success",
        cancel_url="https://example.org/checkout/cancel",
        portal_return_url="https://example.org/account",
    )


def make_event(event_type="checkout.session.completed", livemode=False):
    return json.dumps({
        "id": "evt_test_123",
        "livemode": livemode,
        "type": event_type,
        "data": {"object": {"id": "cs_test_123"}},
    }, separators=(",", ":")).encode()


def sign(body, secret="whsec_test_only", timestamp=1700000000):
    payload = str(timestamp).encode() + b"." + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.mark.parametrize("key", ["sk_live_would_charge", "rk_test_restricted", ""])
def test_gateway_rejects_non_test_secret_key(key):
    with pytest.raises(StripeTestError, match="TEST secret"):
        StripeTestSettings(
            secret_key=key, price_id="price_test",
            webhook_secret="whsec_test",
            success_url="https://example.org/success",
            cancel_url="https://example.org/cancel",
            portal_return_url="https://example.org/account",
        )


@pytest.mark.parametrize("url", ["http://example.org", "javascript:alert(1)", "//example.org"])
def test_gateway_rejects_insecure_redirect_url(url):
    with pytest.raises(StripeTestError, match="HTTPS"):
        StripeTestSettings(
            secret_key="sk_test_abc", price_id="price_test",
            webhook_secret="whsec_abc",
            success_url=url,
            cancel_url="https://example.org/cancel",
            portal_return_url="https://example.org/account",
        )


def test_gateway_checkout_never_sends_raw_whatsapp_id_or_uses_live_key(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "cs_test_123",
                "url": "https://checkout.stripe.com/c/pay/cs_test_123",
                "livemode": False,
            }

    def fake_post(url, *, data, auth, timeout):
        calls.append((url, data, auth))
        return FakeResponse()

    monkeypatch.setattr("app.billing.stripe_test.httpx.post", fake_post)
    result = StripeTestGateway(settings()).create_checkout("15551234567")
    assert result == {"url": "https://checkout.stripe.com/c/pay/cs_test_123",
                      "session_id": "cs_test_123"}
    assert len(calls) == 1
    url, data, auth = calls[0]
    assert url == "https://api.stripe.com/v1/checkout/sessions"
    assert auth == ("sk_test_test_only", "")
    assert data["mode"] == "subscription"
    assert data["client_reference_id"] == hashlib.sha256(
        b"15551234567"
    ).hexdigest()
    assert "15551234567" not in repr(data)
    assert data["line_items[0][price]"] == "price_test_subscription"


def test_gateway_rejects_live_mode_stripe_response(monkeypatch):
    class LiveResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"livemode": True, "url": "https://checkout.stripe.com/c/pay/cs_live"}

    monkeypatch.setattr("app.billing.stripe_test.httpx.post",
                        lambda *args, **kwargs: LiveResponse())
    with pytest.raises(StripeTestError, match="test-mode"):
        StripeTestGateway(settings()).create_checkout("15551234567")


def test_gateway_sanitizes_transport_errors(monkeypatch):
    def failure(*args, **kwargs):
        raise httpx.ConnectError("secret sk_test_hidden")

    monkeypatch.setattr("app.billing.stripe_test.httpx.post", failure)
    with pytest.raises(StripeTestError) as exc:
        StripeTestGateway(settings()).create_checkout("15551234567")
    assert "sk_test_hidden" not in str(exc.value)


def test_valid_signature_accepts_only_test_events_and_multiple_v1_signatures():
    body = make_event()
    header = sign(body) + ",v1=invalid"
    assert verify_test_webhook(
        body, header, "whsec_test_only", now=1700000000
    )["type"] == "checkout.session.completed"


@pytest.mark.parametrize("header", [
    None,
    "",
    "t=1700000000,v1=invalid",
    "t=1700000000,t=1700000000,v1=invalid",
])
def test_bad_signature_is_rejected(header):
    with pytest.raises(StripeTestError):
        verify_test_webhook(
            make_event(), header, "whsec_test_only", now=1700000000
        )


def test_signature_cannot_be_replayed_outside_five_minutes():
    body = make_event()
    for now in [1699999699, 1700000301]:
        with pytest.raises(StripeTestError, match="tolerance"):
            verify_test_webhook(body, sign(body), "whsec_test_only", now=now)


def test_live_mode_signed_event_rejected_even_with_valid_signature():
    body = make_event(livemode=True)
    with pytest.raises(StripeTestError, match="test events"):
        verify_test_webhook(
            body, sign(body), "whsec_test_only", now=1700000000
        )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(internal_api, "INTERNAL_API_TOKEN", "test-admin")
    monkeypatch.setattr(billing, "STRIPE_TEST_MODE_ENABLED", True)
    monkeypatch.setattr(billing, "STRIPE_TEST_SECRET_KEY", settings().secret_key)
    monkeypatch.setattr(billing, "STRIPE_TEST_PRICE_ID", settings().price_id)
    monkeypatch.setattr(billing, "STRIPE_TEST_WEBHOOK_SECRET", settings().webhook_secret)
    monkeypatch.setattr(billing, "STRIPE_TEST_SUCCESS_URL", settings().success_url)
    monkeypatch.setattr(billing, "STRIPE_TEST_CANCEL_URL", settings().cancel_url)
    monkeypatch.setattr(
        billing, "STRIPE_TEST_PORTAL_RETURN_URL", settings().portal_return_url
    )
    class UnlinkedStore:
        def find_checkout(self, _session_id):
            return None

        def get_test_subscription(self, _whatsapp_id):
            return None

    monkeypatch.setattr(billing, "_store", lambda: UnlinkedStore())
    yield TestClient(app)


def test_billing_endpoints_disabled_by_default(monkeypatch):
    monkeypatch.setattr(billing, "STRIPE_TEST_MODE_ENABLED", False)
    test_client = TestClient(app)
    body = make_event()
    assert test_client.post(
        "/api/v1/billing/test/webhook", content=body,
        headers={"Stripe-Signature": sign(body, timestamp=int(time()))},
    ).status_code == 404


def test_checkout_rejects_unauthorized_and_portal_requires_linked_customer(
    client, monkeypatch,
):
    path = "/api/v1/billing/test/checkout"
    assert client.post(path, json={"whatsapp_id": "15551234567"}).status_code == 401
    assert client.post(
        path,
        json={"whatsapp_id": "15551234567"},
        headers={"Authorization": "Bearer wrong"},
    ).status_code == 401
    assert client.post(
        "/api/v1/billing/test/portal",
        json={"whatsapp_id": "15551234567"},
        headers={"Authorization": "Bearer test-admin"},
    ).status_code == 404


def test_valid_signed_webhook_is_observational_and_does_not_grant_premium(client):
    sender = "15551234567"
    subscription_service.store.clear()
    before = subscription_service.get_subscription(sender)
    body = make_event()
    response = client.post(
        "/api/v1/billing/test/webhook", content=body,
        headers={"Stripe-Signature": sign(body, timestamp=int(time()))},
    )
    assert response.status_code == 200
    assert response.json() == {"received": True, "applied": False}
    assert subscription_service.get_subscription(sender) == before
    assert not subscription_service.get_subscription(sender).has_premium_access


def test_tampered_webhook_is_rejected_and_cannot_change_entitlements(client):
    sender = "15551234567"
    before = subscription_service.get_subscription(sender)
    body = make_event()
    response = client.post(
        "/api/v1/billing/test/webhook", content=body + b" ",
        headers={"Stripe-Signature": sign(body, timestamp=int(time()))},
    )
    assert response.status_code == 400
    assert subscription_service.get_subscription(sender) == before
