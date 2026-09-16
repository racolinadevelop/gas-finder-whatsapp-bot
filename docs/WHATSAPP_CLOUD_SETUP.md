# WhatsApp Cloud API Setup

This document explains how to configure WhatsApp Cloud API for the Gas Finder Bot project.

The production version of the project uses:

- Meta WhatsApp Business Platform
- FastAPI
- Railway
- Google Places API (New)

## Current Architecture

```text
WhatsApp User
      ↓
Meta WhatsApp Business Platform
      ↓
Railway Public URL
      ↓
FastAPI Webhook
      ↓
Google Places API
      ↓
Gas station results
      ↓
WhatsApp response
```

The production backend is currently deployed at:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app
```

Swagger documentation is available at:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app/docs
```

---

# 1. Create the Meta App

Go to Meta for Developers and create an app.

The current project uses:

```text
Gas Finder Bot
```

Select the WhatsApp business messaging use case.

Connect the app to a Meta Business Portfolio.

---

# 2. Configure WhatsApp Business Platform

Inside the Meta developer dashboard:

1. Open the WhatsApp use case.
2. Configure WhatsApp Cloud API.
3. Request a test phone number.
4. Add a test recipient.
5. Send the initial test message.

Meta will provide information such as:

- Phone Number ID
- WhatsApp Business Account ID
- Access Token

Never publish these credentials.

---

# 3. Environment Variables

The application requires the following environment variables:

```env
GOOGLE_MAPS_API_KEY=

WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_API_VERSION=
WHATSAPP_VERIFY_TOKEN=
```

The real values must never be committed to GitHub.

Local development uses:

```text
.env
```

The repository contains:

```text
.env.example
```

so other developers know which variables are required.

---

# 4. WhatsApp Access Token

The temporary token generated from the WhatsApp testing page expires and should only be used during early development.

The production configuration uses a Meta System User.

## Create a System User

Go to:

```text
Meta Business Settings
→ Users
→ System Users
```

Create a system user for the backend.

Example:

```text
GasFinderBackend2026
```

Assign the following assets:

- Gas Finder Bot app
- WhatsApp Business Account

The WhatsApp account should have the minimum permissions necessary for messaging.

## Generate the Access Token

Generate a token for:

```text
Gas Finder Bot
```

Use the following permissions:

```text
whatsapp_business_management
whatsapp_business_messaging
```

Store the generated token as:

```env
WHATSAPP_ACCESS_TOKEN=
```

Do not publish or commit the token.

---

# 5. Webhook Verification Token

The project uses a custom verification token.

Example environment variable:

```env
WHATSAPP_VERIFY_TOKEN=YOUR_VERIFY_TOKEN
```

This value is created by the developer.

Meta uses it to verify that the webhook belongs to the application.

The FastAPI webhook verification endpoint is:

```http
GET /api/v1/whatsapp/webhook
```

Meta sends parameters such as:

```text
hub.mode
hub.verify_token
hub.challenge
```

If the verification token matches, FastAPI returns the challenge.

---

# 6. Receiving WhatsApp Webhooks

Incoming WhatsApp events are sent to:

```http
POST /api/v1/whatsapp/webhook
```

The application currently recognizes:

```text
text
location
```

For a location message, the application extracts:

```text
latitude
longitude
sender
message_id
```

The coordinates are then passed to the Gas Finder service.

---

# 7. Subscribe to Messages

Inside Meta Webhooks:

1. Select:

   ```text
   WhatsApp Business Account
   ```

2. Configure the callback URL.

3. Subscribe to:

   ```text
   messages
   ```

The Meta app must also be subscribed to the WhatsApp Business Account.

This can be verified using the Meta Graph API endpoint:

```text
/{WABA-ID}/subscribed_apps
```

---

# 8. Local Development

For local development, run FastAPI with:

```bash
uvicorn app.main:app --reload
```

The local API runs at:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

---

# 9. Cloudflare Tunnel During Development

During early development, Cloudflare Quick Tunnel was used to expose the local FastAPI server to Meta.

Example command:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Cloudflare generated temporary URLs similar to:

```text
https://example.trycloudflare.com
```

The callback URL would then be:

```text
https://example.trycloudflare.com/api/v1/whatsapp/webhook
```

## Important

Quick Tunnel URLs are temporary.

If the tunnel stops or restarts, the URL may change.

This requires manually updating the Meta webhook configuration.

Because of this limitation, Cloudflare Quick Tunnel is no longer used for the production version of Gas Finder Bot.

---

# 10. Railway Production Deployment

The FastAPI backend is deployed on Railway.

The production URL is:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app
```

The Meta webhook callback URL is:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app/api/v1/whatsapp/webhook
```

This URL remains stable and does not depend on the developer's computer being online.

---

# 11. Railway Environment Variables

The same environment variables from the local `.env` file must be configured in Railway.

Required variables:

```text
GOOGLE_MAPS_API_KEY
WHATSAPP_ACCESS_TOKEN
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_BUSINESS_ACCOUNT_ID
WHATSAPP_API_VERSION
WHATSAPP_VERIFY_TOKEN
```

Do not upload `.env` to Railway or GitHub.

Configure the variables through the Railway project settings.

---

# 12. Railway Start Command

The project contains:

```text
railway.toml
```

The production server starts with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Railway automatically provides the `PORT` environment variable.

---

# 13. Production Flow

When a user sends their location through WhatsApp:

```text
User shares location
        ↓
WhatsApp
        ↓
Meta webhook
        ↓
Railway
        ↓
FastAPI
        ↓
Extract latitude and longitude
        ↓
Google Places API
        ↓
Retrieve nearby gas stations
        ↓
Calculate distance and estimated cost
        ↓
Sort results
        ↓
Format WhatsApp message
        ↓
Send response to user
```

---

# 14. Current Bot Behavior

When a text message is received, the bot asks the user to share their location.

Example:

```text
Hi! 👋
Send me your location and I'll find nearby gas stations for you.
```

When a location is received, the backend searches for nearby gas stations.

The current default settings are approximately:

```text
Fuel type: Regular
Search radius: 5000 meters
Sort: Best
Maximum results: 5
Gallons needed: 10
Vehicle MPG: 25
```

Future versions will allow users to change these settings through WhatsApp commands.

---

# 15. Security

Never commit:

```text
.env
Google API keys
WhatsApp access tokens
private credentials
```

Use:

```text
.env
```

for local development and Railway environment variables for production.

If a credential is accidentally exposed, revoke or rotate it immediately.

---

# 16. Testing

Run the automated tests with:

```bash
python -m pytest -v
```

The project includes tests for:

- input validation
- Google Places failures
- empty results
- fuel price sorting
- distance sorting
- best-option calculation
- WhatsApp message formatting
- incoming WhatsApp messages

---

# 17. Production Testing

The production API can be checked at:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app
```

Swagger:

```text
https://gas-finder-whatsapp-bot-production.up.railway.app/docs
```

The final production test is:

1. Stop local Uvicorn.
2. Stop Cloudflare Tunnel.
3. Send a real location through WhatsApp.
4. Confirm that Railway receives the webhook.
5. Confirm that the bot returns real nearby gas stations.

If this works, the system is operating independently from the developer's local computer.

---

# 18. Current Production Status

The following components are operational:

```text
Google Places API ✅
FastAPI REST API ✅
Fuel prices ✅
Distance calculation ✅
Best-option calculation ✅
WhatsApp Cloud API ✅
Incoming WhatsApp webhooks ✅
Location messages ✅
Automatic WhatsApp replies ✅
System User Access Token ✅
Railway deployment ✅
Stable webhook URL ✅
```

Cloudflare Quick Tunnel is no longer required for production.