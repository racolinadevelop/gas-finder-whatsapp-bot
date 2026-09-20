"""Reconcile signed Stripe TEST events against server-bound Checkout sessions.

Never provision access from webhook payload alone: retrieve current Checkout
and Subscription using sk_test_, enforce stored checkout-to-user binding,
test-mode status, linked customer, configured Price and paid invoice.
"""

from app.billing.stripe_test import StripeTestError, StripeTestGateway
from app.billing.test_store import PostgresTestBillingStore, TestBillingStoreError


HANDLED_EVENTS = frozenset({
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.created",
    "invoice.paid",
    "invoice.payment_failed",
})


def _id(value: object, prefix: str) -> str | None:
    if isinstance(value, dict):
        value = value.get("id")
    if isinstance(value, str) and value.startswith(prefix) and value.isascii():
        return value
    return None


def _subscription_id(event: dict) -> str | None:
    event_type = event["type"]
    obj = event["data"]["object"]
    if event_type.startswith("customer.subscription."):
        return _id(obj.get("id"), "sub_")
    if event_type.startswith("invoice."):
        # Stripe API versions can place the subscription under invoice.parent.
        parent = obj.get("parent")
        details = parent.get("subscription_details") if isinstance(parent, dict) else None
        return _id(
            obj.get("subscription") or (
                details.get("subscription") if isinstance(details, dict) else None
            ),
            "sub_",
        )
    return None


def _current_status(
    subscription: dict,
    *,
    customer_id: str,
    subscription_id: str,
    price_id: str,
) -> str:
    if subscription.get("livemode") is not False or subscription.get("id") != subscription_id:
        raise StripeTestError("Test subscription identity verification failed")
    if _id(subscription.get("customer"), "cus_") != customer_id:
        raise StripeTestError("Test subscription customer does not match Checkout")

    items = subscription.get("items")
    entries = items.get("data") if isinstance(items, dict) else None
    prices = [
        _id(row.get("price"), "price_")
        for row in entries if isinstance(row, dict)
    ] if isinstance(entries, list) else []
    if price_id not in prices:
        # A user can change their subscription items in a test portal. Revoke
        # access rather than leaving previously paid Premium active indefinitely.
        return "inactive"

    status = subscription.get("status")
    if status in {"canceled", "incomplete_expired"}:
        return "canceled"
    if status in {"past_due", "unpaid", "incomplete"}:
        return "past_due"
    if status != "active":
        return "inactive"

    # A subscription with a trial, free invoice, or unpaid renewal cannot
    # grant the paid test entitlement. No reliance on client redirect.
    invoice = subscription.get("latest_invoice")
    if (
        not isinstance(invoice, dict)
        or invoice.get("livemode") is not False
        or invoice.get("paid") is not True
        or invoice.get("status") != "paid"
        or not isinstance(invoice.get("amount_paid"), int)
        or invoice["amount_paid"] <= 0
        or _id(invoice.get("subscription"), "sub_") not in {None, subscription_id}
    ):
        return "inactive"
    return "active"


class StripeTestReconciler:
    def __init__(
        self,
        gateway: StripeTestGateway,
        store: PostgresTestBillingStore,
    ) -> None:
        self.gateway = gateway
        self.store = store

    def reconcile(self, event: dict) -> bool:
        """Return True only if a known linked test subscription was updated."""
        if event.get("livemode") is not False or event.get("type") not in HANDLED_EVENTS:
            return False

        event_type = event["type"]
        obj = event["data"]["object"]
        if event_type.startswith("checkout.session."):
            session_id = _id(obj.get("id"), "cs_test_")
            if session_id is None:
                return False
            bound = self.store.find_checkout(session_id)
            if bound is None:
                return False
            user_digest, previous_customer, previous_subscription = bound
            checkout = self.gateway.get_checkout(session_id)
            customer_id = _id(checkout.get("customer"), "cus_")
            subscription_id = _id(checkout.get("subscription"), "sub_")
            if (
                checkout.get("status") != "complete"
                or checkout.get("mode") != "subscription"
                or checkout.get("payment_status") != "paid"
                or checkout.get("client_reference_id") != user_digest
                or customer_id is None
                or subscription_id is None
                or (previous_customer is not None and previous_customer != customer_id)
                or (previous_subscription is not None and previous_subscription != subscription_id)
            ):
                return False
        else:
            subscription_id = _subscription_id(event)
            if subscription_id is None:
                return False
            bound = self.store.find_subscription(subscription_id)
            if bound is None:
                # An invoice or subscription event may arrive before Checkout;
                # completed Checkout will fetch current Stripe state itself.
                return False
            session_id, _user_digest, customer_id = bound
            checkout = self.gateway.get_checkout(session_id)
            if (
                checkout.get("status") != "complete"
                or checkout.get("mode") != "subscription"
                or checkout.get("payment_status") != "paid"
                or _id(checkout.get("customer"), "cus_") != customer_id
                or _id(checkout.get("subscription"), "sub_") != subscription_id
            ):
                return False
        current = self.gateway.get_subscription(subscription_id)
        status = _current_status(
            current,
            customer_id=customer_id,
            subscription_id=subscription_id,
            price_id=self.gateway.settings.price_id,
        )
        return self.store.apply_verified_state(
            event_id=event["id"],
            session_id=session_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            status=status,
        )
