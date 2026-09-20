# Gas Finder WhatsApp Bot

![Tests](https://github.com/racolinadevelop/gas-finder-whatsapp-bot/actions/workflows/tests.yml/badge.svg)

A backend project built with Python and FastAPI that helps users find nearby gas stations, compare available fuel prices, and receive the results directly through WhatsApp.

The application is connected to the Meta WhatsApp Business Platform and can use Google Places API (New) or HERE Fuel Prices API to retrieve real gas station information.

## Live API

Production backend:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app
```

Swagger documentation is intended for local development and can be disabled
in production with `API_DOCS_ENABLED=false`.

## Current Architecture

The FastAPI entry point is intentionally small. WhatsApp conversation routing,
prompt delivery, station lookup, state storage and subscription policy live in
separate modules, with `app/handlers/whatsapp.py` acting as the composition root.

```text
WhatsApp / Meta
     ↓
FastAPI route: signature verification
     ↓
Webhook parse + deduplication + subscription identity
     ↓
Message type router → conversation state router
     ↓
Guided choices / search decision → location search
     ↓
Google Places or HERE provider → localized results
     ↓
WhatsApp response (primary prompt, then Back/Menu when appropriate)
```

See [Architecture and refactor closeout](docs/ARCHITECTURE.md) for module
boundaries, preserved behaviors, automated tests and the live smoke-test checklist.

## Current Features

- Search nearby gas stations using latitude and longitude
- Receive user location directly from WhatsApp
- Retrieve real gas station information from the configured provider
- Retrieve available fuel prices
- Keep provider price-update timestamps for internal price metadata, but show
  concise WhatsApp result cards without timestamp or opening-hour labels
- Support:
  - Regular
  - Premium
  - Diesel
- Calculate approximate distance in miles
- When the separately billed Routes API is enabled, show actual driving miles
  as the main distance and an approximate ETA; re-rank the five displayed
  candidates by driving distance or driving-based estimated cost
- Search up to three Google Places pages by default (one or two can be configured
  to save calls, with reduced station coverage)
- Sort gas stations by:
  - Distance
  - Price
  - Best estimated option
- Estimate travel cost based on:
  - Fuel price
  - Distance
  - Gallons needed
  - Vehicle MPG
- Evaluate a larger candidate set before selecting the displayed results
- Exclude stations without a price for the selected fuel
- Deduplicate provider results that represent the same address
- Switch between Google Places and HERE Fuel Prices through configuration
- Validate API query parameters
- Handle Google Places errors and timeouts
- Receive WhatsApp webhook events
- Detect text and location messages
- Interpret natural-language searches in English and Spanish
- Understand a requested maximum distance in miles or kilometers
- Offer a guided WhatsApp distance list with 1, 3, 5, 10 miles or a custom value
- Explain why the top "Best option" balances price and travel distance
- Exclude Google stations explicitly marked closed or non-operational; retain
  unknown-hour stations without claiming they are open
- Keep guided-search preferences when navigating Back or retrying after a provider failure
- Remember completed search settings separately from conversation state, and
  restore them when a returning user sends a location after session expiry
- Ignore repeated WhatsApp message IDs and rate-limit station searches per user
- Maintain a centralized Free/Premium subscription and feature-access foundation (billing not yet connected)
- Keep language interpretation separate from deterministic station lookup
- Optionally use an OpenAI Structured Outputs fallback for ambiguous messages
- Send automatic WhatsApp replies
- Deployed on Railway with a stable public URL
- Automated testing with pytest
- Interactive API documentation with Swagger

## Technologies

- Python 3.13.15
- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- Google Places API (New)
- HERE Fuel Prices API v3
- Meta WhatsApp Business Platform
- Railway
- Redis
- PostgreSQL
- Psycopg
- python-dotenv
- pytest
- Git
- GitHub

## Project Structure

```text
gas-finder-whatsapp-bot/
├── app/
│   ├── main.py               # FastAPI application factory / health
│   ├── config.py              # Environment and production validation
│   ├── routers/               # HTTP routes and Meta webhook signature
│   ├── handlers/              # Webhook, text, buttons, location and results
│   ├── routing/               # Message-type and conversation-state routers
│   ├── conversation/          # States, transitions and search decisions
│   ├── models/                # Normalized incoming messages
│   ├── parsers/               # Meta payload normalization
│   ├── presentation/          # Localized prompts and WhatsApp delivery
│   ├── intelligence/          # Deterministic and optional AI intent parsing
│   ├── services/              # Station lookup and WhatsApp transport
│   ├── providers/             # Gas-station provider interface / HERE
│   ├── persistence/           # Redis client
│   ├── rate_limits/           # Search throttling
│   ├── webhooks/              # Message deduplication
│   ├── subscriptions/         # Free/Premium state and access policy
│   └── utils/
├── docs/                      # Architecture, provider and setup guides
├── tests/                     # Unit, API and simulated webhook flow tests
├── .github/workflows/tests.yml
├── .env.example
├── railway.toml
├── README.md
└── requirements.txt
```

## Local Installation

Clone the repository:

```bash
git clone https://github.com/racolinadevelop/gas-finder-whatsapp-bot.git
```

Enter the project directory:

```bash
cd gas-finder-whatsapp-bot
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Configuration

Create your local environment file:

```bash
cp .env.example .env
```

Configure:

```env
GOOGLE_MAPS_API_KEY=
GAS_STATION_PROVIDER=google
HERE_API_KEY=

WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_API_VERSION=
WHATSAPP_VERIFY_TOKEN=
META_APP_SECRET=
INTERNAL_API_TOKEN=

# Keep true for local Swagger/OpenAPI; set false in production.
API_DOCS_ENABLED=true

# Optional locally; required in production for persistent runtime state.
REDIS_URL=
REDIS_KEY_PREFIX=gas-finder
CONVERSATION_TTL_SECONDS=604800
WHATSAPP_DEDUP_TTL_SECONDS=86400

# Per-user gas-station search rate limiting.
SEARCH_RATE_LIMIT_MAX=10
SEARCH_RATE_LIMIT_WINDOW_SECONDS=300

# Google Places Text Search: 1–3 pages, default 3 for station coverage.
GOOGLE_TEXT_MAX_PAGES=3

# Separate paid Routes API: opt in only after enabling the service in Google
# Cloud and reviewing matrix-element billing; independent of Places search.
ROUTES_API_ENABLED=false
ROUTES_MAX_DESTINATIONS=5

# Optional locally; use Railway PostgreSQL in production for subscriptions.
DATABASE_URL=
```

Never commit `.env`.

### Gas-station data provider

Google remains the default provider. It uses Places Text Search with up to
three pages of 20 candidates each by default (configurable from one to three
pages), enforces the requested radius locally,
removes duplicate addresses and stations without a selected-fuel price, then
sorts and displays the requested number of results. Explicitly closed or
non-operational Google stations are excluded; stations with unknown hours
remain as labeled fallback results.

To test HERE Fuel Prices instead, obtain a HERE API key and configure:

```env
GAS_STATION_PROVIDER=here
HERE_API_KEY=your_here_api_key
```

Only one provider is active at a time. Compare both providers at the same
location, radius, fuel type, and time before changing production. See
`docs/GAS_STATION_PROVIDERS.md` for the verification checklist.

### Optional AI intent fallback

The deterministic interpreter is always available and does not require an API
key. To enable the model fallback only for ambiguous messages, configure:

```env
AI_INTENT_ENABLED=true
OPENAI_API_KEY=your_test_key
OPENAI_MODEL=gpt-6-astra
```

The model only returns a validated search intent. It does not receive tools and
cannot search for or invent gas-station results. If the API is unavailable, the
bot continues with the deterministic interpreter.

### Free and Premium foundation

Every WhatsApp user starts on the Free plan. Access decisions are centralized
in `SubscriptionService`, which currently keeps the existing gas search,
directions, and basic comparison available for free. Future features such as
favorites, price alerts, price history, advanced comparisons, and personalized
recommendations are defined as Premium capabilities.

Subscription records use PostgreSQL when `DATABASE_URL` is configured.
Without it, local development and tests continue to use in-memory storage.
The PostgreSQL table is created automatically at startup and stores a SHA-256
identifier instead of the raw WhatsApp ID. No payment provider or real billing
is connected yet; Stripe Sandbox can be added behind the same service later.

## Run Locally

Start FastAPI:

```bash
uvicorn app.main:app --reload
```

Local Swagger:

```text
http://127.0.0.1:8000/docs
```

## Main Gas Station Endpoint

```http
GET /api/v1/gas-stations/nearby
Authorization: Bearer <INTERNAL_API_TOKEN>
```

The REST gas-station endpoint is internal-only. It requires the same
`INTERNAL_API_TOKEN` used by the manual WhatsApp send endpoint, preventing
unauthenticated callers from consuming the configured gas-station provider
quota. The WhatsApp conversation flow does not call this HTTP endpoint; it
uses the station-search service directly.

Supported parameters:

```text
latitude
longitude
radius
fuel_type
sort
limit
gallons_needed
vehicle_mpg
```

### Fuel Types

```text
regular
premium
diesel
```

### Sorting Options

```text
distance
price
best
```

## WhatsApp Webhook

Webhook verification:

```http
GET /api/v1/whatsapp/webhook
```

Internal manual message endpoint:

```http
POST /api/v1/whatsapp/send-message
Authorization: Bearer <INTERNAL_API_TOKEN>
```

This endpoint is disabled unless `INTERNAL_API_TOKEN` is configured and
rejects requests without the matching bearer token.

Incoming WhatsApp events:

```http
POST /api/v1/whatsapp/webhook
```

When `META_APP_SECRET` is configured, incoming POST webhook payloads are
validated against Meta's `X-Hub-Signature-256` signature before the event is
processed. Local development can leave the variable empty.

Production callback URL:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app/api/v1/whatsapp/webhook
```

## Current WhatsApp Flow

A greeting starts the guided conversation rather than requesting location
immediately:

```text
"hola" / "hello"
       ↓
Select English / Español
       ↓
Select regular / premium / diesel
       ↓
Select closest / cheapest / best estimated option
       ↓
Select 1 / 3 / 5 / 10 miles or a valid custom distance
       ↓
Share location through WhatsApp's native location request
       ↓
Search selected provider; show priced stations and available hours status
       ↓
Results + Back (new location with saved preferences) / Menu (restart)
```

The bot also accepts supported natural-language search requests. Back/Menu
work across the guided flow; stale buttons or inputs from the wrong step
re-prompt the expected screen without replacing saved preferences.
When a search provider fails, users can share their location again with
their preferences preserved.

## Example Bot Response

```text
⛽ Nearby gas stations

1. Example Station
   💵 $2.899/gal
   📍 0.72 mi

2. Example Station
   💵 $2.999/gal
   📍 1.14 mi
```

## Automated Tests

GitHub Actions runs the full pytest suite automatically on every push to
`main` and on every pull request. The CI workflow uses test-only environment
values and does not require production secrets. A separate dependency audit
also checks `requirements.txt` for known Python package vulnerabilities.
Dependabot checks direct Python dependencies and GitHub Actions weekly and can
open controlled update pull requests. Internal transitive packages are left to
their parent dependency resolver so incompatible component-only upgrades are
not proposed independently.

Run locally:

```bash
python -m pytest -v
```

The test suite covers:

- coordinate validation
- search limit validation
- empty search results
- Google Places timeouts
- authentication errors
- rate limits
- connection errors
- sorting by distance
- sorting by price
- price tie breaking
- best-option calculation
- WhatsApp text replies
- WhatsApp gas station message formatting
- Meta webhook signature validation and duplicate-event handling
- guided conversation state, Back/Menu and out-of-sequence input recovery
- Spanish and English HTTP webhook journeys with faked external APIs, including
  custom distance, search failure and preserved preferences

## Documentation

Architecture, module responsibilities and post-deployment smoke tests:

[Architecture and Refactor Closeout](docs/ARCHITECTURE.md)

Google request budgets, paid route opt-in and billing safeguards:

[API Costs and Routes](docs/API_COSTS_AND_ROUTES.md)

Gas station providers and operating-hours behavior:

[Gas Station Providers](docs/GAS_STATION_PROVIDERS.md)

Google Places setup:

[Google Places Setup](docs/GOOGLE_PLACES_SETUP.md)

API usage:

[API Usage Guide](docs/API_USAGE.md)

WhatsApp Cloud API setup:

[WhatsApp Cloud Setup](docs/WHATSAPP_CLOUD_SETUP.md)

Privacy policy:

[Privacy Policy](docs/PRIVACY_POLICY.md)

## Deployment

The production backend is hosted on Railway.

Railway starts the application with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The configuration is defined in:

```text
railway.toml
```

Production credentials are stored using Railway environment variables.

For shared conversation state, webhook deduplication, and per-user search
rate limiting, add a Redis service to the Railway project and expose its
connection URL to the application as `REDIS_URL`. When configured,
conversations remain available for seven days and processed WhatsApp message
IDs for 24 hours by default. Real gas-station searches are limited to 10 per
user in a five-minute window by default. These values can be changed with the
environment variables shown above. The application checks the Redis connection
during startup so an invalid configuration fails before it begins accepting
webhooks.

For persistent Free/Premium state, add a PostgreSQL service to the Railway
project and expose its connection URL to the application as `DATABASE_URL`.
When configured, the app creates the subscription table automatically and
uses PostgreSQL instead of in-memory subscription storage.

Cloudflare Quick Tunnel was used during early development but is no longer required for production.

## Current Production Status

```text
Google Places API ✅
FastAPI REST API ✅
Fuel prices ✅
Distance calculation ✅
Best-option calculation ✅
Error handling ✅
Automated tests ✅
WhatsApp Cloud API ✅
Incoming webhooks ✅
Location messages ✅
Automatic WhatsApp replies ✅
System User Access Token ✅
Railway deployment ✅
Stable production URL ✅
Redis-ready persistent conversation state ✅
Redis-ready cross-instance webhook deduplication ✅
PostgreSQL-ready persistent subscription state ✅
```

## Current Limitations

- With Routes disabled, the bot labels its geographic distance as approximate.
  Once Google Routes is enabled, the main distance is the driving route and
  "closest"/"best" are recalculated among the five preselected stations using
  their available routes. If a route fails, the bot says driving distance is
  unavailable rather than passing off geographic miles as a road route.
  Route estimates exclude live traffic. Provider candidate selection and
  the requested search radius remain geographic to cap Routes billing, so a
  station outside the preselected five cannot be discovered by road ranking;
  actual road distance may exceed the chosen search radius.
- Three Places pages improve coverage but do not guarantee that a particular
  station is returned. Set `GOOGLE_TEXT_MAX_PAGES=1` or `=2` for fewer API
  requests at the cost of potentially missing stations and cheaper prices.
- Completed guided searches store preferred language, fuel, sorting, and radius
  in a separate user profile (PostgreSQL in production). After the temporary
  conversation expires, sending a new location reuses that profile. A first-time
  user without saved preferences still uses defaults. Menu starts a fresh guided
  search and does not silently preload previous choices; a new completed guided
  search replaces the saved profile.
- Station prices and opening hours depend on provider coverage and freshness.
  Unknown hours are not proof that a station is open. HERE does not verify
  real-time open status.
- Free/Premium policy and storage are present. An opt-in Stripe TEST-only
  Checkout/portal adapter and signed, observational test webhook are available;
  payment-to-user binding, event reconciliation and paid feature enforcement
  are not implemented yet. No real payments are collected by this project.
- Automated tests mock external Meta/Google/HERE calls. A live WhatsApp
  smoke test is still required after deployment; see
  [Architecture and Refactor Closeout](docs/ARCHITECTURE.md).

## Roadmap

The guided WhatsApp conversation and initial modularization are implemented.
Next product stages, in planned order:

1. Complete post-refactor automated regression checks and the live WhatsApp
   smoke test after deployment.
2. Enable Google Routes in the Cloud project and opt in on Railway to show
   real driving distance/ETA and driving-based ranking among the five displayed
   candidates. Verify real WhatsApp results and API-element costs before
   increasing traffic or widening the candidate pool.
3. Keep price timestamps as internal provider metadata; the simplified WhatsApp
   display intentionally hides update-time and opening-hour labels.
4. User-level language, fuel, sorting and radius preferences now persist
   separately from the active conversation (implemented).
5. Stripe TEST-only Checkout/portal transport and signed webhook validation
   are prepared behind a disabled-by-default flag. Next: persist a verified
   Checkout-to-user binding, process lifecycle events idempotently, and gate
   Premium features after confirmed paid status. Never enable live billing
   before cancellation/renewal and test-mode end-to-end checks.
6. Add favorites/history and price alerts, assigning appropriate Free/Premium
   access before enabling real charges.
7. Automate reusable Meta/WhatsApp onboarding and improve production
   monitoring, API costs and deployment verification.

The current Free/Premium records and feature enum are architecture groundwork,
not a functioning payment integration or a promise of features already delivered.

## Production Configuration Validation

Set `APP_ENV=production` in Railway to enable strict startup validation.
Production startup requires the WhatsApp access token and phone number ID,
webhook verify token, Meta App Secret, internal API token, Redis URL, and
PostgreSQL URL. API documentation must also be disabled. Missing critical
configuration stops startup immediately instead of allowing a partially
configured service to accept traffic.

## Production Logging

Application logs intentionally avoid storing WhatsApp message text, user names,
phone numbers, or location coordinates. Operational logs record only technical
events such as message type, provider failures, duplicate webhook handling,
rate-limit events, and aggregate search counts.

## Security

Never commit:

- `.env`
- API keys
- WhatsApp access tokens
- private credentials
- Meta App Secret
- internal API tokens

Use environment variables for all secrets.

If a credential is exposed accidentally, rotate it immediately.

## Status

Project currently in active development.

Stripe TEST-only integration and staged activation: [Billing Test Setup](docs/STRIPE_TEST_BILLING.md).
