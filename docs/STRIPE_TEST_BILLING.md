# Stripe sandbox: test subscriptions without real payments

The Stripe integration runs **only when explicitly enabled** and accepts only
`sk_test_` keys and signed `livemode:false` webhook events. It never changes
`user_subscriptions` (real/normal records): verified TEST payments update a
separate PostgreSQL sandbox entitlement ledger. With the flag disabled, any
sandbox Premium access is ignored. The current WhatsApp gas-station search
remains free and unchanged. No real payment features or public self-service
checkout have been activated.

## 1. Run automated tests with no Stripe account

From your cloned repository with Python and `requirements.txt` installed:

```bash
python -m pytest -q tests/test_stripe_test_billing.py tests/test_stripe_sandbox_lifecycle.py
python -m pytest -q
```

These tests simulate actual signed webhook HTTP deliveries, Checkout identity
binding, durable SQL records, paid/unpaid status, duplicates, renewal, payment
failure, cancelation, wrong users, bad Price IDs and live-mode rejection. They
make **no real Stripe, Meta or Google API calls**. A passing test suite alone
does not prove your actual Stripe account is configured correctly.

## 2. Optional REAL Stripe sandbox payment test

**Never use a live API key or your real credit card.** Stripe's test/sandbox
environment simulates payment processing without moving real money. It is
separate from its live account. See Stripe's official test-card guidance:
https://docs.stripe.com/testing

1. In Stripe Dashboard, switch to **Sandbox / test mode**. Create a
   **recurring**, **nonzero-price** USD product/Price and copy its `price_...` ID.
   Use that sandbox's `sk_test_...` secret key.
2. Create a Stripe webhook destination in **test mode** pointing to
   `https://YOUR_RAILWAY_DOMAIN/api/v1/billing/test/webhook`. Include event
   types `checkout.session.completed`, `invoice.paid`,
   `invoice.payment_failed`, `customer.subscription.updated` and
   `customer.subscription.deleted`. Copy the destination's `whsec_...`
   signing secret. A different webhook destination has a different secret.
3. Configure the following values **in Railway service variables**, NOT in Git
   or this chat, and allow the bot to deploy. Your existing `DATABASE_URL`
   PostgreSQL and `INTERNAL_API_TOKEN` must already be configured.

   ```dotenv
   STRIPE_TEST_MODE_ENABLED=true
   STRIPE_TEST_SECRET_KEY=sk_test_...
   STRIPE_TEST_PRICE_ID=price_...
   STRIPE_TEST_WEBHOOK_SECRET=whsec_...
   STRIPE_TEST_SUCCESS_URL=https://YOUR_RAILWAY_DOMAIN/
   STRIPE_TEST_CANCEL_URL=https://YOUR_RAILWAY_DOMAIN/
   STRIPE_TEST_PORTAL_RETURN_URL=https://YOUR_RAILWAY_DOMAIN/
   ```

   The root URL is an existing temporary return destination suitable for a
   smoke test (it returns a short API message, **not** payment confirmation).
   Replace it with branded HTTPS landing pages before public release.

4. On your own computer set `GAS_FINDER_BASE_URL` to the HTTPS URL of your
   Railway bot and `SANDBOX_TEST_WHATSAPP_ID` to the WhatsApp test user you
   own. Export your existing `INTERNAL_API_TOKEN` securely; **never share it
   here, put it in screenshots or commit it**. Run:

   ```bash
   python scripts/stripe_sandbox_smoke.py checkout
   ```

   The admin-only endpoint creates a TEST Checkout Session and persists the
   immutable Checkout Session ID ↔ hashed test WhatsApp user mapping
   **before** returning its link. Open that link in your browser.
5. Use a Stripe test card such as **4242 4242 4242 4242**, any valid future
   expiration date and any 3-digit CVC. Use made-up test contact details.
   In Stripe Dashboard confirm the subscription and webhook delivery.
   The success redirect is **not proof of payment**.
6. Verify that the signed webhook was received and that the app fetched
   the actual TEST Checkout and current subscription from Stripe. Run:

   ```bash
   python scripts/stripe_sandbox_smoke.py status
   ```

   Expected for an approved paid/active subscription:
   `Sandbox linked: True`, `Sandbox subscription status: active`,
   `Sandbox Premium feature access: True`. Normal subscription records
   remain untouched. WhatsApp now offers a read-only **Mi plan / My plan** button at language
   selection and commands `mi plan` / `my plan` at any step. It reports the
   verified Free/Premium test status without changing the current search.
   This status view is not a public payment flow or a Premium-only feature;
   the admin status endpoint remains the sandbox integration smoke check.
7. Try `python scripts/stripe_sandbox_smoke.py portal` to obtain the
   authenticated user's Stripe TEST customer portal link. Cancel the
   subscription *immediately* in the Stripe test portal, or use Stripe
   dashboard test controls. Verify `status` becomes `canceled` and sandbox
   access becomes `False`. **Cancellation at period end retains active
   entitlement until Stripe reports it actually canceled**; use immediate
   cancellation for a quick revocation test. Test payment failures/renewals
   separately with Stripe test tools.

The `/checkout`, `/portal` and `/status` endpoints require your existing
`Authorization: Bearer <INTERNAL_API_TOKEN>` header, and are intended only
for your trusted local admin script. The webhook needs the Stripe signature,
not the internal token. Do not expose the admin token in a client application.

## Important safeguards and current test-stage limitations

- Only a stored server-created Checkout Session association can link a
  subscription to a user. Webhook event data, client redirect, request body,
  and arbitrary Stripe metadata cannot grant access on their own.
- Current TEST subscription `status=active`, an invoice marked paid with a
  positive amount, customer ID, and configured Price must match the actual
  Stripe objects fetched using `sk_test_`. Unpaid, trial, unknown and
  canceled states cannot grant sandbox Premium.
- Processed Stripe event IDs are stored in PostgreSQL in the same transaction
  as a sandbox entitlement change. Early unlinked invoice events are ignored;
  a later completed Checkout reconciles Stripe's current subscription state.
  Duplicate events cannot apply twice.
- A test user may link only one subscription in this sandbox version. An
  existing linked customer uses its test portal; onboarding a **new**
  subscription after immediate cancellation currently requires a new test
  WhatsApp user or a controlled cleanup of the test-only tables.
- This implementation is a sandbox, **not production billing**. Production
  would require a truly authenticated public self-service journey, robust
  reconciliation for concurrent and out-of-order webhooks, separate live
  subscription records, a secure secret-management process, and full price
  and cancellation acceptance tests. Do **not** enable live billing keys.
- Disabling `STRIPE_TEST_MODE_ENABLED` restores Free-only feature checks for
  users whose sole entitlement came from this sandbox. It does not delete
  their test records; re-enabling the flag will read those records again.
