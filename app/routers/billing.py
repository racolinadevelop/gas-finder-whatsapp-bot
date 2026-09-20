"""Admin-only Stripe test-mode sessions and observational signed webhook.

Important: This milestone does not change user plan, subscription status,
or provision Premium. Webhook reconciliation requires a persistent checkout
binding and idempotent subscription lifecycle handling in a later milestone.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.billing import (
    StripeTestError,
    StripeTestGateway,
    StripeTestSettings,
    verify_test_webhook,
)
from app.config import (
    STRIPE_TEST_MODE_ENABLED,
    STRIPE_TEST_SECRET_KEY,
    STRIPE_TEST_PRICE_ID,
    STRIPE_TEST_WEBHOOK_SECRET,
    STRIPE_TEST_SUCCESS_URL,
    STRIPE_TEST_CANCEL_URL,
    STRIPE_TEST_PORTAL_RETURN_URL,
)
from app.handlers.whatsapp import subscription_service
from app.security import require_internal_api_token


router = APIRouter(prefix="/api/v1/billing/test", tags=["billing-test"])


class BillingUserRequest(BaseModel):
    whatsapp_id: str = Field(min_length=5, max_length=20, pattern=r"^[0-9]+$")


def _gateway() -> StripeTestGateway:
    if not STRIPE_TEST_MODE_ENABLED:
        raise HTTPException(status_code=404, detail="Test billing is disabled.")
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
        # Never return secret values in error messages.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return StripeTestGateway(settings)


@router.post(
    "/checkout",
    dependencies=[Depends(require_internal_api_token)],
)
def create_test_checkout(payload: BillingUserRequest):
    gateway = _gateway()
    subscription = subscription_service.get_subscription(payload.whatsapp_id)
    if subscription.has_premium_access:
        raise HTTPException(status_code=409, detail="User already has Premium.")
    try:
        return gateway.create_checkout(
            payload.whatsapp_id,
            customer_id=subscription.billing_customer_id,
        )
    except StripeTestError as exc:
        raise HTTPException(
            status_code=502, detail="Stripe test checkout unavailable."
        ) from exc


@router.post(
    "/portal",
    dependencies=[Depends(require_internal_api_token)],
)
def create_test_portal(payload: BillingUserRequest):
    gateway = _gateway()
    subscription = subscription_service.get_subscription(payload.whatsapp_id)
    if not subscription.billing_customer_id:
        raise HTTPException(
            status_code=404,
            detail="No linked billing customer for this user.",
        )
    try:
        return gateway.create_portal(subscription.billing_customer_id)
    except StripeTestError as exc:
        raise HTTPException(
            status_code=502, detail="Stripe test billing portal unavailable."
        ) from exc


@router.post("/webhook")
async def receive_test_stripe_webhook(request: Request):
    # Strict opt-in; no public webhook processing unless configured.
    if not STRIPE_TEST_MODE_ENABLED:
        raise HTTPException(status_code=404, detail="Test billing is disabled.")
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

    # Do not apply events or trust client_reference_id without a persisted,
    # server-created Checkout Session association to a WhatsApp account.
    # Stripe retries and event order must be handled in the next milestone.
    return {"received": True, "applied": False}
