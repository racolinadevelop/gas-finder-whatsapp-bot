# Gas Finder WhatsApp Bot

A backend project built with Python and FastAPI that helps users find nearby gas stations, compare available fuel prices, and receive the results directly through WhatsApp.

The application is connected to the Meta WhatsApp Business Platform and uses Google Places API (New) to retrieve real gas station information.

## Live API

Production backend:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app
```

Swagger documentation:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app/docs
```

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
Google Places API
      ↓
Gas station results
      ↓
WhatsApp response
```

## Current Features

- Search nearby gas stations using latitude and longitude
- Receive user location directly from WhatsApp
- Retrieve real gas station information from Google Places
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
- Handle stations without available fuel prices
- Validate API query parameters
- Handle Google Places errors and timeouts
- Receive WhatsApp webhook events
- Detect text and location messages
- Interpret natural-language searches in English and Spanish
- Keep language interpretation separate from deterministic station lookup
- Optionally use an OpenAI Structured Outputs fallback for ambiguous messages
- Send automatic WhatsApp replies
- Deployed on Railway with a stable public URL
- Automated testing with pytest
- Interactive API documentation with Swagger

## Technologies

- Python
- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- Google Places API (New)
- Meta WhatsApp Business Platform
- Railway
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
│   ├── routers/
│   ├── routing/
│   ├── services/
│   │   ├── google_places.py
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

WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_API_VERSION=
WHATSAPP_VERIFY_TOKEN=
```

Never commit `.env`.

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
```

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

Incoming WhatsApp events:

```http
POST /api/v1/whatsapp/webhook
```

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

Run:

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
- PostgreSQL database
- Search history
- Favorite gas stations
- Fuel price alerts
- Improved WhatsApp conversational flow
- Docker
- Additional production monitoring

## Security

Never commit:

- `.env`
- API keys
- WhatsApp access tokens
- private credentials

Use environment variables for all secrets.

If a credential is exposed accidentally, rotate it immediately.

## Status

Project currently in active development.
