# Stripe TEST-mode billing foundation (not live or provisioned)

This milestone prepares an isolated Stripe Billing integration **without
collecting real payments, activating Premium, or changing the existing bot
conversation**. All billing endpoints are disabled by default.

## Available now

- `POST /api/v1/billing/test/checkout`: administrative, bearer-token-protected
  creation of a Stripe-hosted TEST subscription Checkout Session. Request body
  `{"whatsapp_id": "<test WhatsApp phone digits>"}`; returns a short-lived test
  Checkout URL. Only use test-card details, never a real card.
- `POST /api/v1/billing/test/portal`: administrative, bearer-token-protected
  customer portal URL, only for an already linked billing customer.
- `POST /api/v1/billing/test/webhook`: accepts only signed test-mode events
  whose Stripe-Signature matches the **exact raw body** and whose timestamp
  is no more than five minutes from server time. It currently returns
  `{"received": true, "applied": false}` and does **not** alter any user plan.

The server-side Checkout request only sends a SHA-256 hash of a test user's
WhatsApp identifier to Stripe, not the raw phone number or location.

The existing Free/Premium access policy remains unchanged; no Premium feature
is granted from a Checkout redirect, test payment, or webhook event at this stage.

## Configuration and security

No Stripe variables are enabled or set in production by this code change.
Leave `STRIPE_TEST_MODE_ENABLED=false` until ready for a controlled test.

To enable **only test mode**, create a recurring test Price in the Stripe
test/sandbox account, configure its test customer portal, and set these secure
environment variables (never commit the values):

```dotenv
STRIPE_TEST_MODE_ENABLED=true
STRIPE_TEST_SECRET_KEY=sk_test_...
STRIPE_TEST_PRICE_ID=price_...
STRIPE_TEST_WEBHOOK_SECRET=whsec_...
STRIPE_TEST_SUCCESS_URL=https://YOUR_DOMAIN/checkout/success
STRIPE_TEST_CANCEL_URL=https://YOUR_DOMAIN/checkout/cancel
STRIPE_TEST_PORTAL_RETURN_URL=https://YOUR_DOMAIN/account
```

Use HTTPS URLs that you control; create those landing pages separately. The
Stripe webhook endpoint must be registered in **test mode** with URL
`https://YOUR_DOMAIN/api/v1/billing/test/webhook`. Configure the events
`checkout.session.completed`, `customer.subscription.updated`,
`customer.subscription.deleted`, `invoice.paid`, and
`invoice.payment_failed` for upcoming subscription lifecycle tests.

Checkout/portal endpoints also require
`Authorization: Bearer <INTERNAL_API_TOKEN>`. They are intended for a
trusted, authenticated admin or future authenticated self-service app, **not**
for direct public WhatsApp links. Never send the internal token to a user.
Stripe redirect success pages are **not proof of payment**.

A `sk_live_` key, an unsigned webhook, a stale signature, and a signed
`livemode:true` event are all rejected. Existing WhatsApp and Google Maps
settings are untouched.

## Next milestone before granting Premium

1. Create a durable, server-side binding from a Stripe Checkout Session ID to
   its requesting user (identified by a hash in PostgreSQL). Never accept a
   user identity solely because a signed Checkout event has unverified metadata.
2. Record processed Stripe event IDs and update entitlements transactionally,
   including safe retries, duplicates, failed payments, renewals, subscription
   cancellation, asynchronous payment, and out-of-order event delivery.
3. Reconcile actual subscription and invoice state from Stripe's test API;
   enable feature gates only after a verified paid/active subscription.
4. Add secure user-specific checkout and portal entry points outside WhatsApp,
   then test the full cancellation/renewal lifecycle in test mode.

**No real payments should be activated before those steps and user acceptance
testing are complete.**
