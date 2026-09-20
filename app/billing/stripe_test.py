"""Isolated Stripe TEST-mode Checkout/Portal transport and signed webhook verifier.

Verified Stripe TEST webhooks can update the separate sandbox entitlement
ledger only after a durable Checkout-to-user binding and paid-status validation.
No live billing or general user subscription record is modified.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


STRIPE_API = "https://api.stripe.com/v1"
WEBHOOK_TOLERANCE_SECONDS = 300
MAX_WEBHOOK_BYTES = 256 * 1024


class StripeTestError(Exception):
    """Configuration, transport or signature validation failed."""


@dataclass(frozen=True, slots=True)
class StripeTestSettings:
    secret_key: str
    price_id: str
    webhook_secret: str
    success_url: str
    cancel_url: str
    portal_return_url: str

    def __post_init__(self) -> None:
        if not self.secret_key.startswith("sk_test_"):
            raise StripeTestError("Only Stripe TEST secret keys are permitted")
        if not self.price_id.startswith("price_"):
            raise StripeTestError("STRIPE_TEST_PRICE_ID must be a Price ID")
        if not self.webhook_secret.startswith("whsec_"):
            raise StripeTestError("STRIPE_TEST_WEBHOOK_SECRET is missing")
        for url in (self.success_url, self.cancel_url, self.portal_return_url):
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username:
                raise StripeTestError("Billing redirect URLs must use HTTPS")


def verify_test_webhook(
    raw_body: bytes,
    signature_header: str | None,
    webhook_secret: str,
    *,
    now: int | None = None,
) -> dict:
    """Verify Stripe's raw-body HMAC, strict timestamp tolerance and TEST mode."""
    if not webhook_secret.startswith("whsec_"):
        raise StripeTestError("Webhook signing secret not configured")
    if not raw_body or len(raw_body) > MAX_WEBHOOK_BYTES:
        raise StripeTestError("Invalid webhook payload size")
    if not signature_header:
        raise StripeTestError("Missing Stripe-Signature header")

    values: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        key, separator, value = part.strip().partition("=")
        if separator:
            values.setdefault(key, []).append(value)

    try:
        if len(values.get("t", [])) != 1:
            raise ValueError("Missing or ambiguous timestamp")
        timestamp = int(values["t"][0])
    except (ValueError, KeyError) as exc:
        raise StripeTestError("Invalid webhook timestamp") from exc

    clock = int(time.time()) if now is None else now
    if timestamp <= 0 or abs(clock - timestamp) > WEBHOOK_TOLERANCE_SECONDS:
        raise StripeTestError("Webhook timestamp outside tolerance")
    signed = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed, hashlib.sha256
    ).hexdigest()
    signatures = values.get("v1", [])
    if not signatures or not any(
        hmac.compare_digest(expected, candidate) for candidate in signatures
    ):
        raise StripeTestError("Webhook signature is invalid")

    try:
        event = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise StripeTestError("Invalid webhook JSON") from exc
    if (
        not isinstance(event, dict)
        or event.get("livemode") is not False
        or not isinstance(event.get("id"), str)
        or not event["id"].startswith("evt_")
        or not isinstance(event.get("type"), str)
        or not isinstance(event.get("data"), dict)
        or not isinstance(event["data"].get("object"), dict)
    ):
        raise StripeTestError("Only well-formed Stripe test events are accepted")
    return event


class StripeTestGateway:
    """Call Stripe with a TEST secret key; never perform API calls on import."""

    def __init__(self, settings: StripeTestSettings) -> None:
        self.settings = settings

    def _post(self, path: str, data: dict[str, str]) -> dict:
        try:
            response = httpx.post(
                STRIPE_API + path,
                data=data,
                auth=(self.settings.secret_key, ""),
                timeout=15.0,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never surface Stripe response bodies or keys to API clients/logs.
            raise StripeTestError("Stripe test request failed") from exc
        if not isinstance(result, dict) or result.get("livemode") is not False:
            raise StripeTestError("Stripe did not return a test-mode object")
        return result

    def create_checkout(
        self,
        whatsapp_id: str,
        *,
        customer_id: str | None = None,
    ) -> dict:
        """Create an admin-requested Stripe-hosted TEST subscription checkout."""
        if not whatsapp_id.isascii() or not whatsapp_id.isdigit() or not (
            5 <= len(whatsapp_id) <= 20
        ):
            raise StripeTestError("Invalid WhatsApp user identifier")
        customer_reference = hashlib.sha256(whatsapp_id.encode()).hexdigest()
        data = {
            "mode": "subscription",
            "line_items[0][price]": self.settings.price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": customer_reference,
            "success_url": self.settings.success_url,
            "cancel_url": self.settings.cancel_url,
            "payment_method_types[0]": "card",
        }
        if customer_id:
            if not customer_id.startswith("cus_"):
                raise StripeTestError("Invalid billing customer")
            data["customer"] = customer_id
        result = self._post("/checkout/sessions", data)
        url = result.get("url")
        if (
            not isinstance(result.get("id"), str)
            or not result["id"].startswith("cs_test_")
            or not isinstance(url, str)
            or not url.startswith("https://checkout.stripe.com/")
        ):
            raise StripeTestError("Stripe did not return a valid TEST Checkout")
        return {"url": url, "session_id": result["id"]}

    def create_portal(self, customer_id: str) -> dict:
        """Use only a previously linked customer from the subscription store."""
        if not customer_id.startswith("cus_"):
            raise StripeTestError("Invalid billing customer")
        result = self._post(
            "/billing_portal/sessions",
            {
                "customer": customer_id,
                "return_url": self.settings.portal_return_url,
            },
        )
        url = result.get("url")
        if not isinstance(url, str) or not url.startswith("https://billing.stripe.com/"):
            raise StripeTestError("Stripe did not return a test portal URL")
        return {"url": url}

    def _get(self, path: str, *, params: dict | None = None) -> dict:
        """Retrieve an authoritative current TEST object from Stripe."""
        try:
            response = httpx.get(
                STRIPE_API + path,
                params=params,
                auth=(self.settings.secret_key, ""),
                timeout=15.0,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StripeTestError("Stripe test verification unavailable") from exc
        if not isinstance(result, dict) or result.get("livemode") is not False:
            raise StripeTestError("Stripe verification did not return a TEST object")
        return result

    def get_checkout(self, session_id: str) -> dict:
        if not session_id.startswith("cs_test_") or not session_id.isascii():
            raise StripeTestError("Invalid test Checkout session")
        result = self._get(f"/checkout/sessions/{session_id}")
        if result.get("id") != session_id:
            raise StripeTestError("Stripe test Checkout identity mismatch")
        return result

    def get_subscription(self, subscription_id: str) -> dict:
        if not subscription_id.startswith("sub_") or not subscription_id.isascii():
            raise StripeTestError("Invalid test subscription")
        result = self._get(
            f"/subscriptions/{subscription_id}",
            params={"expand[]": "latest_invoice"},
        )
        if result.get("id") != subscription_id:
            raise StripeTestError("Stripe test subscription identity mismatch")
        return result
