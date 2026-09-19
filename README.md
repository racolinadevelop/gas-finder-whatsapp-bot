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

```text
WhatsApp User
      ↓
Meta WhatsApp Business Platform
      ↓
Railway
      ↓
FastAPI
      ↓
Configured station provider
      ↓
Gas station results
      ↓
WhatsApp response
```

## Current Features

- Search nearby gas stations using latitude and longitude
- Receive user location directly from WhatsApp
- Retrieve real gas station information from the configured provider
- Retrieve available fuel prices
- Support:
  - Regular
  - Premium
  - Diesel
- Calculate approximate distance in miles
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
- Maintain a centralized Free/Premium subscription and feature-access foundation
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
│   ├── config.py
│   ├── main.py
│   ├── schemas.py
│   ├── conversation/
│   ├── handlers/
│   ├── intelligence/
│   │   ├── interpreter.py
│   │   └── models.py
│   ├── models/
│   ├── parsers/
│   ├── providers/
│   ├── routers/
│   ├── routing/
│   ├── subscriptions/
│   ├── services/
│   │   ├── google_places.py
│   │   ├── stations.py
│   │   └── whatsapp.py
│   └── utils/
├── docs/
│   ├── API_USAGE.md
│   ├── GOOGLE_PLACES_SETUP.md
│   ├── PRIVACY_POLICY.md
│   └── WHATSAPP_CLOUD_SETUP.md
├── tests/
├── .env.example
├── .gitignore
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

# Optional locally; use Railway PostgreSQL in production for subscriptions.
DATABASE_URL=
```

Never commit `.env`.

### Gas-station data provider

Google remains the default provider. It now fetches up to 20 nearby candidates,
then removes duplicates and stations without a price before sorting and showing
the requested number of results.

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

When the user sends a text message:

```text
User
 ↓
"hello"
 ↓
Bot asks for location
```

When the user shares a location:

```text
WhatsApp location
      ↓
FastAPI webhook
      ↓
Latitude + longitude
      ↓
Google Places
      ↓
Gas stations
      ↓
Price + distance + best calculation
      ↓
Formatted WhatsApp message
      ↓
User
```

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
values and does not require production secrets.

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

## Documentation

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

The current MVP calculates geographic straight-line distance.

It does not yet calculate actual driving distance.

The bot currently uses default search preferences when the user sends a location.

Future versions will allow the user to configure these preferences directly through WhatsApp.

## Roadmap

Planned features include:

- WhatsApp commands:
  - regular
  - premium
  - diesel
  - closest
  - cheapest
  - best
- User preferences
- Actual driving distance
- Search history
- Favorite gas stations
- Fuel price alerts
- Improved WhatsApp conversational flow
- Docker
- Additional production monitoring

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
