# Gas Finder architecture and refactor closeout

This document describes the production code after the WhatsApp handler
refactor. `app/main.py` is the FastAPI application factory; it is not the
conversation controller.

## Request and conversation flow

```text
Meta WhatsApp event
  -> app/routers/whatsapp.py
       HTTP webhook verification / optional signature validation
  -> app/handlers/whatsapp.py
       Composition root: existing runtime, transports and callback wiring
  -> app/handlers/webhook_dispatch.py
       Normalize event, deduplicate message ID, ensure user, dispatch
  -> app/parsers/whatsapp.py + app/models/incoming_message.py
       One normalized IncomingMessage (text, interactive, location, media)
  -> app/routing/whatsapp_routers.py
       MessageRouter chooses text / interactive / location / fallback
       ConversationStateRouter chooses the active guided-flow step
  -> app/handlers/text_messages.py / interactive_messages.py /
     location_messages.py / conversation_states.py
       Validate input against current state and choose a transition
  -> app/conversation/
       States, transitions, navigation, distance parsing and search decisions
  -> app/handlers/search_flow_delivery.py or location_results.py
       Apply search decision or run a location search and advance state
  -> app/services/location_search.py -> app/services/stations.py
       Provider-independent lookup -> Google Places or HERE Fuel Prices
  -> app/presentation/prompts.py + app/presentation/delivery.py
       Localized WhatsApp prompt and optional Back / Menu
  -> app/services/whatsapp.py
       Meta Cloud API transport
```

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `app/main.py` | Construct FastAPI app, include routers, root and health endpoints. |
| `app/routers/whatsapp.py` | HTTP endpoint, Meta challenge and POST signature verification. |
| `app/handlers/whatsapp.py` | Wire the existing runtime, intent interpreter, state handlers and message transports. It retains small public callback wrappers used by the HTTP route and regression tests. |
| `app/handlers/webhook_dispatch.py` | Parse and deduplicate incoming events; release a claimed message ID after an unexpected processing exception so Meta can retry. |
| `app/routing/whatsapp_routers.py` | Register the message-type and conversation-state handlers without creating session or API dependencies. |
| `app/handlers/text_messages.py` | Give navigation and greetings precedence; interpret new text only when its active state allows it. |
| `app/handlers/interactive_messages.py` | Route selected buttons and ignore stale language selections outside the language step. |
| `app/handlers/location_messages.py` | Ignore absent coordinates, route valid active-location messages and re-prompt out-of-sequence users. |
| `app/handlers/conversation_states.py` | Execute selections for fuel, sort and distance on the active guided state. |
| `app/conversation/` | Define deterministic state changes, navigation and search-flow decisions. No Meta HTTP calls. |
| `app/handlers/search_flow_delivery.py` | Apply a search-flow decision and send its selected prompt. |
| `app/handlers/location_results.py` | Rate-limit location lookups, format/send results, handle provider/transport errors and advance to results only after sending them. |
| `app/presentation/` | Build localized prompts and deliver primary content before additional navigation buttons. |
| `app/services/`, `app/providers/` | Query gas stations and format results; expose provider errors to the handler. |
| `app/runtime.py`, `app/subscriptions/` | Build the configured stores, deduplicator, rate limiter and Free/Premium access policy. Payment processing is not implemented. |

The small callback wrappers in `app/handlers/whatsapp.py` deliberately pass
live functions to extracted modules. This avoids import cycles and keeps the
existing dependency replacement points used by tests. Avoid moving these
wrappers just to reduce line count; place new business logic in the
appropriate independent module.

## Invariants to preserve

1. Signature verification (when configured) happens before dispatch.
2. Repeated WhatsApp message IDs are acknowledged without duplicate replies.
   Unexpected dispatch failures release their deduplication claim.
3. A greeting opens language selection. Stale language buttons cannot reset
   an active search. Back and Menu are available globally.
4. A custom distance is validated before requesting a location.
5. Unrelated text or an unexpected location does not overwrite selected
   language, fuel, sort or radius.
6. The location request is delivered before Back/Menu; the results view
   sends its own navigation exactly once.
7. A station-provider error or failed result delivery does not advance a
   session to WAITING_RESULTS. Successful delivery preserves preferences for
   another location via Back.
8. Search rate limiting occurs before provider lookup. Subscription access
   remains Free by default; no charges or Premium entitlement are triggered
   by this refactor.

## Verification

From the repository root, after installing `requirements.txt`:

```bash
python -m pytest -v
```

The test suite includes isolated parser, router, prompt, state, provider,
deduplication, error-recovery and subscription tests. In particular,
`tests/test_whatsapp_flow_integration.py` exercises the actual FastAPI
POST webhook -> parser -> deduplicator -> message router -> conversation
transitions -> delivery path, with only external WhatsApp sending, station
lookup and subscription persistence replaced by fakes. It covers Spanish
and English guided journeys, list/button selections, custom distance,
unexpected inputs, duplicate events, provider failure, Back/Menu and a
status-only webhook. The CI workflow runs pytest and a dependency audit
on each pull request and on pushes to main.

These automated tests do not confirm that Meta's live account, the Google/HERE
API, Railway environment or WhatsApp's native location button is working.
After deployment, run the live smoke-test checklist below using a test
WhatsApp number. Never put user phone numbers, precise user locations,
access tokens or payment credentials into test logs or screenshots.

### Live smoke-test checklist (manual, post-deploy)

1. Send `hola` to the connected WhatsApp test number. Choose Español,
   Premium fuel, cheapest sorting and 3 miles. Confirm each prompt and that
   Back/Menu appears below the location request.
2. Send unrelated text while asked for a location; verify the same location
   request returns and saved preferences do not change.
3. Share a real location. Confirm results are received with selected fuel,
   price, station-hours indication when available, and Back/Menu.
4. Tap Back, send another location and confirm another search uses the same
   preferences. Tap Menu and confirm language selection restarts.
5. Start in English, select custom distance, send an invalid value, then
   a valid value. Try an old language button and an unexpected location
   before choosing distance; neither should skip the active step.
6. Check Railway logs for provider/Meta errors without exposing credentials.
   If feasible, repeat with a controlled provider failure and verify a retry
   message that retains preferences.

If any live check fails, investigate before enabling new product features
or billing. Automated green checks alone are not a live-service guarantee.
