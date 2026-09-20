"""Admin-only Stripe sandbox Checkout, portal, status and verified test webhooks.

The test billing ledger is separate from production subscriptions. Only
verified, paid, currently active TEST subscriptions grant sandbox access when
the explicit feature flag is enabled. No public self-service links or live
payment credentials are accepted.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.billing import (
    StripeTestError,
    StripeTestGateway,
    StripeTestSettings,
    verify_test_webhook,
)
from app.billing.test_reconciliation import StripeTestReconciler
from app.billing.test_store import TestBillingStoreError
from app.config import (
    STRIPE_TEST_MODE_ENABLED,
    STRIPE_TEST_SECRET_KEY,
    STRIPE_TEST_PRICE_ID,
    STRIPE_TEST_WEBHOOK_SECRET,
    STRIPE_TEST_SUCCESS_URL,
    STRIPE_TEST_CANCEL_URL,
    STRIPE_TEST_PORTAL_RETURN_URL,
)
from app.handlers.whatsapp import subscription_service, test_billing_store
from app.security import require_internal_api_token


router = APIRouter(prefix="/api/v1/billing/test", tags=["billing-test"])


class BillingUserRequest(BaseModel):
    whatsapp_id: str = Field(min_length=5, max_length=20, pattern=r"^[0-9]+$")


def _store():
    if not STRIPE_TEST_MODE_ENABLED:
        raise HTTPException(status_code=404, detail="Test billing is disabled.")
    if test_billing_store is None:
        raise HTTPException(
            status_code=503,
            detail="Persistent test billing storage is not configured.",
        )
    return test_billing_store


def _gateway() -> StripeTestGateway:
    _store()
    try:
        settings = StripeTestSettings(
            secret_key=STRIPE_TEST_SECRET_KEY,
            price_id=STRIPE_TEST_PRICE_ID,
            webhook_secret=STRIPE_TEST_WEBHOOK_SECRET,
            success_url=STRIPE_TEST_SUCCESS_URL,
            cancel_url=STRIPE_TEST_CANCEL_URL,
            portal_return_url=STRIPE_TEST_PORTAL_RETURN_URL,
        )
    except StripeTestError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StripeTestGateway(settings)


@router.post("/checkout", dependencies=[Depends(require_internal_api_token)])
def create_test_checkout(payload: BillingUserRequest):
    gateway = _gateway()
    store = _store()
    subscription = subscription_service.get_subscription(payload.whatsapp_id)
    previous_test_subscription = store.get_test_subscription(payload.whatsapp_id)
    if (
        subscription.has_premium_access
        or previous_test_subscription is not None
    ):
        # Prevent replacing an immutable test subscription with a different
        # subscription for the same user. Manage the existing one via Portal.
        raise HTTPException(
            status_code=409,
            detail="User already has an associated subscription.",
        )
    try:
        checkout = gateway.create_checkout(payload.whatsapp_id)
        store.save_checkout(checkout["session_id"], payload.whatsapp_id)
        return {"url": checkout["url"]}
    except StripeTestError as exc:
        raise HTTPException(
            status_code=502, detail="Stripe test checkout unavailable."
        ) from exc
    except TestBillingStoreError as exc:
        raise HTTPException(
            status_code=409, detail="Test Checkout binding conflict."
        ) from exc
    except Exception as exc:
        # An unbound Checkout cannot grant access even if paid.
        raise HTTPException(
            status_code=503, detail="Cannot persist test Checkout binding."
        ) from exc


@router.post("/portal", dependencies=[Depends(require_internal_api_token)])
def create_test_portal(payload: BillingUserRequest):
    gateway = _gateway()
    record = _store().get_test_subscription(payload.whatsapp_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="No linked test billing customer.",
        )
    try:
        return gateway.create_portal(record["customer_id"])
    except StripeTestError as exc:
        raise HTTPException(
            status_code=502, detail="Stripe test billing portal unavailable."
        ) from exc


@router.post("/status", dependencies=[Depends(require_internal_api_token)])
def get_test_subscription_status(payload: BillingUserRequest):
    _gateway()
    record = _store().get_test_subscription(payload.whatsapp_id)
    return {
        "test_mode": True,
        "linked": record is not None,
        "status": record["status"] if record else "inactive",
        "sandbox_premium_access": (
            record is not None and record["status"] == "active"
        ),
    }


@router.post("/webhook")
async def receive_test_stripe_webhook(request: Request):
    gateway = _gateway()
    raw_body = await request.body()
    try:
        event = verify_test_webhook(
            raw_body,
            request.headers.get("stripe-signature"),
            STRIPE_TEST_WEBHOOK_SECRET,
        )
    except StripeTestError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid Stripe test webhook."
        ) from exc

    try:
        applied = StripeTestReconciler(gateway, _store()).reconcile(event)
    except (StripeTestError, TestBillingStoreError) as exc:
        # Stripe retries a 5xx event after transient API/database failures.
        # Never trust the event snapshot or mark it processed on failures.
        raise HTTPException(
            status_code=503, detail="Test billing verification unavailable."
        ) from exc
    return {"received": True, "applied": applied}
