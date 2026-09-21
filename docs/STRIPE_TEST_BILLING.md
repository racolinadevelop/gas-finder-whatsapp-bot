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
- This sandbox allows one linked subscription per test user **at a time**.
  To run another paid test after **immediate** cancellation, the admin may
  run `python scripts/stripe_sandbox_smoke.py reset` and then `checkout`
  again. Reset requires the internal API token, the ledger status `canceled`,
  and a fresh Stripe TEST API verification that the linked subscription is
  canceled. It clears only test Checkout bindings and the test entitlement
  for that WhatsApp sender. Previous test event receipts remain recorded;
  favorites, language settings, normal subscriptions and other users are
  untouched. Signed late webhook events for old Checkouts are ignored. This
  is a *test-only administrator reset*, not a production resubscription flow.
- This implementation is a sandbox, **not production billing**. Production
  would require a truly authenticated public self-service journey, robust
  reconciliation for concurrent and out-of-order webhooks, separate live
  subscription records, a secure secret-management process, and full price
  and cancellation acceptance tests. Do **not** enable live billing keys.
- Disabling `STRIPE_TEST_MODE_ENABLED` restores Free-only feature checks for
  users whose sole entitlement came from this sandbox. It does not delete
  their test records; re-enabling the flag will read those records again.


## First Premium WhatsApp feature: saved stations

In a completed WhatsApp gas-station search, a user with **current Premium
access** sees Save 1–5 choices for the same five stations already shown, along
with Back and Menu in a single list. From any conversation step, the user may
type `mis favoritas` / `my favorites` to view saved station names and addresses,
`guardar 1` / `save 1` to save a station from the latest delivered results, or
`eliminar favorita 1` / `remove favorite 1` to remove one. Up to ten favorites
are supported. Search result numbers expire after 24 hours; the saved list
persists across server restarts in PostgreSQL. Stored favorite snapshots contain
station identity, name and address, **not** the user's coordinates, price or
travel history. Favorites are saved from the existing Places/Routes search; no
additional Google API calls are made to save or list them. Saved addresses
are snapshots, not live price or opening-hour information.

Every favorites read/write checks the authenticated WhatsApp sender's
`Feature.FAVORITES` entitlement on the server. An expired or canceled Stripe
test subscription cannot read or mutate favorites, but its saved items remain
for a possible future verified Premium entitlement. Free users retain the
same gas-station search flow and navigation. The initial bilingual `Mi plan`
message has been shortened.

Stripe **test-only** payments remain the only Checkout flow. After
cancellation, an administrator can run `python scripts/stripe_sandbox_smoke.py
reset` and then `python scripts/stripe_sandbox_smoke.py checkout` to repeat
the test with the same WhatsApp user. Reset discards the old *test billing
linkage only* after verifying its Stripe TEST subscription was canceled.
Saved favorite stations and language remain untouched. This is a test-only
workflow, not a general customer resubscription feature. The automated
Premium/Free/canceled favorites tests never require real charges or new
Google API requests.


## WhatsApp home and language preference

The first explicit English/Español selection is saved immediately in a
separate PostgreSQL `user_language_preferences` table using a SHA-256 hash
of the WhatsApp sender ID. This is independent of the expiring conversation
session and does **not** require completing a gas-station search. Existing
search preference profiles and active chats are migrated when read.

After selecting a language, the user sees one localized home menu with
**Find gas stations**, **My favorites**, **My plan**, and **Change language**.
A returning user's greeting or `menu` opens that menu without asking for the
language again. The explicit Change language option (also available via
`cambiar idioma` or `change language`) displays the language selection
buttons and saves the new choice after selection. Back from the fuel screen
returns to home. My favorites always checks the current server-side Premium
entitlement, and basic station searching stays free. Singular requests like
`mi favorita` / `my favorite` are accepted as synonyms for the list.
No new Places or Routes API requests are made by language or menu actions.


## One-tap navigation for account and favorites

The `Mi plan / My plan` response now sends a concise status message followed by
a WhatsApp list with **Find gas stations**, **My favorites**, **Change language**
and **Main menu**. Before the first language selection it offers the language
buttons instead. The `Mis favoritas / My favorites` response likewise sends
a localized actions list, including a Remove option when there are saved
favorites. Free users receive the Premium-access notice and a list that lets
them continue searching or view their plan without typing.

Remove opens a five-at-a-time picker (with Next/Previous when needed) for up to
ten saved favorites. Each picker selection identifies a specific saved station
rather than an index, so tapping an old picker cannot remove the station that
later shifted into that position. Back returns to Favorites, and Menu always
returns to the remembered-language home screen. Search from any account view
starts the existing fuel-selection flow. None of these views requests new
Google Places or Routes data, changes the stored language, or enables live
Stripe billing.


## Compare Premium favorites on demand

The **Compare favorites / Comparar favoritas** option is available from the
saved-favorites WhatsApp list with active Premium (including Stripe **TEST**
entitlements). The user selects the first five or, when present, favorites
6–10, chooses Regular/Premium/Diesel, then explicitly shares a WhatsApp location.
The feature **never** auto-refreshes or monitors prices. The comparison rechecks
the sender's Premium entitlement and the existing per-user search rate limit
immediately before making billable provider requests. Canceling Premium while
waiting for location blocks all comparison API calls.

For a comparison of N selected saved Google stations (1 <= N <= 5), the
service requests **at most N Google Place Details (New) responses**, by saved
place ID with a narrow field mask. It does **not** call Places Text Search,
search across a new radius, or re-fetch other favorites. If the separately
configured Routes API is on, it may also call **one Routes matrix** for at
most N currently operational stations with valid coordinates; its matrix
elements are separately billable. In particular, fetching `fuelOptions` in
Place Details uses Google's higher-priced Place Details Enterprise + Atmosphere
SKU: unlike merely opening the saved list, **comparing favorites is not free
of Google API usage**. Keep this manual, bounded comparison and check actual
Google Cloud billing before enabling it broadly.

The response sorts available USD fuel prices first, reports Google's price
update time (or explicitly says that it is unknown), and shows real driving
miles/ETA only when Routes returns an actual route. Unavailable prices, closed
stations, unsupported older favorite IDs and missing routes are labeled; an
old saved price, geographic straight-line distance or made-up route is never
shown as current data. Only station identity, name and address remain saved:
the location, fetched prices and computed routes are not persisted. The
normal **free** gas-station search remains unchanged. Under the alternative
HERE provider this Google-place-ID comparison is unavailable; it does not
silently send HERE station IDs to Google.


## One-tap Stripe **TEST** signup from WhatsApp (sandbox only)

When `STRIPE_TEST_MODE_ENABLED=true` AND the additional explicit
`STRIPE_TEST_WHATSAPP_LINKS_ENABLED=true` flag are configured in Railway,
the localized **My plan / Mi plan** list offers **Try Premium / Probar
Premium** to users with no active subscription. Clicking this option
generates a *new, user-specific Stripe TEST Checkout Session on the server*,
stores the Checkout Session ID ↔ hashed incoming WhatsApp sender association,
then sends that sender a clickable Stripe-hosted HTTPS link privately in
WhatsApp. No number, billing customer, price ID or feature entitlement can
be chosen by typing into the chat or by editing the returned URL.
The existing signed Stripe test webhook still re-queries current paid/active
status; clicking the Checkout link or returning to the bot does not unlock
Premium by itself. User coordinates, saved favorites and gas-search context
remain unchanged; merely opening My plan or a Checkout link makes no Google
Places/Routes calls.

A repeated click on Try Premium for the same user reuses their existing open
Checkout Session instead of creating another subscription. A completed
Checkout awaiting webhook verification never triggers a second Checkout.
The flow requires a shared per-sender Redis lock and fails closed if Redis
is unavailable. A **verified already-canceled TEST subscription** can
re-enroll on the same number after Stripe confirms cancellation: only its
old test Checkout/entitlement binding is cleared; saved favorites and
language are preserved. An active or unpaid/past-due linked account cannot
buy a second subscription. Currently active sandbox subscribers see
**Manage test plan / Gestionar prueba** instead, which creates a private
Stripe TEST Billing Portal link for their linked customer.

This is NOT an enablement of real payment processing or public onboarding.
Stripe settings reject live secret keys and only accept test-mode webhook
events. WhatsApp's current Meta test number can reach only allowlisted
test recipients. The plan is still a TEST purchase: use Stripe test card
details only, never a real card. Leave `STRIPE_TEST_WHATSAPP_LINKS_ENABLED`
off until the trusted sandbox setup and UI are verified; the default is
disabled. For production subscriptions we still need a distinct live-mode
onboarding, clearly disclosed real price/renewal terms, billing acceptance
tests and customer-support/cancellation process. Do not switch a TEST secret
to a live key to bypass these steps.
