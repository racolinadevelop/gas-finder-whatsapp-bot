"""Opt-in TEST-only Stripe links requested by the verified WhatsApp sender.

The server, not any WhatsApp message text, binds a fresh Checkout session to
the webhook sender. Redis locks prevent duplicate sessions across workers.
Live Stripe credentials are rejected by StripeTestSettings and gateway.
"""

import logging
from hashlib import sha256

from app.billing.stripe_test import StripeTestGateway, StripeTestSettings, StripeTestError
from app.billing.test_store import TestBillingStoreError, user_hash
from app.config import (
    REDIS_KEY_PREFIX, REDIS_URL, STRIPE_TEST_MODE_ENABLED,
    STRIPE_TEST_WHATSAPP_LINKS_ENABLED, STRIPE_TEST_SECRET_KEY,
    STRIPE_TEST_PRICE_ID, STRIPE_TEST_WEBHOOK_SECRET,
    STRIPE_TEST_SUCCESS_URL, STRIPE_TEST_CANCEL_URL,
    STRIPE_TEST_PORTAL_RETURN_URL,
)
from app.persistence.redis_client import build_redis_client
from app.billing.whatsapp_receipts import remember_test_checkout_recipient

logger = logging.getLogger(__name__)


class WhatsAppTestCheckoutError(Exception):
    """A safe, non-sensitive reason why a TEST link cannot be sent."""


def links_enabled() -> bool:
    return STRIPE_TEST_MODE_ENABLED and STRIPE_TEST_WHATSAPP_LINKS_ENABLED


def test_gateway() -> StripeTestGateway:
    return StripeTestGateway(StripeTestSettings(
        secret_key=STRIPE_TEST_SECRET_KEY,
        price_id=STRIPE_TEST_PRICE_ID,
        webhook_secret=STRIPE_TEST_WEBHOOK_SECRET,
        success_url=STRIPE_TEST_SUCCESS_URL,
        cancel_url=STRIPE_TEST_CANCEL_URL,
        portal_return_url=STRIPE_TEST_PORTAL_RETURN_URL,
    ))


def _is_stripe_test_url(url: object, *, portal: bool = False) -> bool:
    from urllib.parse import urlparse

    if not isinstance(url, str) or len(url) > 2048:
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme == "https" and parsed.username is None
        and parsed.password is None and parsed.port is None
        and parsed.hostname == (
            "billing.stripe.com" if portal else "checkout.stripe.com"
        )
        and parsed.path.startswith("/p/" if portal else "/c/")
        # Real Stripe-hosted Checkout URLs may carry an essential #fragment.
        # Keep the full returned URL intact so it opens correctly on mobile.
    )


def create_sender_checkout(
    sender: str, *, store, subscription_service,
    gateway: StripeTestGateway | None = None, redis_client=None,
) -> str:
    """Return a bound existing/new test checkout URL, never user-supplied IDs."""
    if not links_enabled() or store is None:
        raise WhatsAppTestCheckoutError("disabled")
    if not sender.isascii() or not sender.isdigit() or not 5 <= len(sender) <= 20:
        raise WhatsAppTestCheckoutError("invalid")
    if not REDIS_URL and redis_client is None:
        # A distributed lock is mandatory in production; never fail open.
        raise WhatsAppTestCheckoutError("unavailable")
    try:
        client = redis_client if redis_client is not None else build_redis_client(REDIS_URL)
        # Uses a hashed sender, never stores raw phone numbers in Redis.
        with client.lock(
            f"{REDIS_KEY_PREFIX}:test-checkout:{sha256(sender.encode()).hexdigest()}",
            timeout=75, blocking_timeout=1,
        ):
            gateway = gateway or test_gateway()
            if subscription_service.get_subscription(sender).has_premium_access:
                raise WhatsAppTestCheckoutError("already_premium")
            record = store.get_test_subscription(sender)
            if record is not None:
                if record["status"] != "canceled":
                    raise WhatsAppTestCheckoutError("already_linked")
                verified = gateway.get_subscription(record["subscription_id"])
                customer = verified.get("customer")
                if isinstance(customer, dict):
                    customer = customer.get("id")
                if (
                    verified.get("livemode") is not False
                    or verified.get("id") != record["subscription_id"]
                    or customer != record["customer_id"]
                    or verified.get("status") != "canceled"
                ):
                    raise WhatsAppTestCheckoutError("already_linked")
                # Only TEST linkage is cleared, never favorites/language.
                store.reset_canceled_user(
                    sender, customer_id=record["customer_id"],
                    subscription_id=record["subscription_id"],
                )

            pending = store.find_latest_pending_checkout(sender)
            if pending:
                current = gateway.get_checkout(pending)
                if (
                    current.get("livemode") is not False
                    or current.get("id") != pending
                    or current.get("client_reference_id") != user_hash(sender)
                ):
                    raise WhatsAppTestCheckoutError("unavailable")
                if current.get("status") == "open":
                    url = current.get("url")
                    if not _is_stripe_test_url(url):
                        raise WhatsAppTestCheckoutError("unavailable")
                    remember_test_checkout_recipient(
                        sender, pending, redis_client=client,
                    )
                    return url
                if current.get("status") != "expired":
                    # Completed but webhook not reconciled: do not offer
                    # another subscription or grant access from a redirect.
                    raise WhatsAppTestCheckoutError("processing")
            result = gateway.create_checkout(sender)
            url = result.get("url")
            if not _is_stripe_test_url(url) or not result.get("session_id", "").startswith("cs_test_"):
                raise WhatsAppTestCheckoutError("unavailable")
            store.save_checkout(result["session_id"], sender)
            remember_test_checkout_recipient(
                sender, result["session_id"], redis_client=client,
            )
            return url
    except WhatsAppTestCheckoutError:
        raise
    except (StripeTestError, TestBillingStoreError):
        logger.warning("Sandbox Checkout verification or binding failed")
        raise WhatsAppTestCheckoutError("unavailable") from None
    except Exception:
        # Includes Redis unavailable/lock contention; never create an
        # unguarded second subscription or expose credentials/details.
        logger.warning("Sandbox Checkout request unavailable")
        raise WhatsAppTestCheckoutError("unavailable") from None


def create_sender_portal(
    sender: str, *, store, gateway: StripeTestGateway | None = None,
) -> str:
    if not links_enabled() or store is None:
        raise WhatsAppTestCheckoutError("disabled")
    try:
        record = store.get_test_subscription(sender)
        if record is None or record["status"] not in {"active", "past_due"}:
            raise WhatsAppTestCheckoutError("not_linked")
        gateway = gateway or test_gateway()
        result = gateway.create_portal(record["customer_id"])
        url = result.get("url")
        if not _is_stripe_test_url(url, portal=True):
            raise WhatsAppTestCheckoutError("unavailable")
        return url
    except WhatsAppTestCheckoutError:
        raise
    except Exception:
        logger.warning("Sandbox billing portal unavailable")
        raise WhatsAppTestCheckoutError("unavailable") from None
