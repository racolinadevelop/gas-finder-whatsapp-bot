# Google API cost controls and road routes

## Current server-side API request budget

Each actual gas-station search uses **one to three** Google Places Text
Search requests by default (up to 20 candidates per page). The provider
stops earlier if there is no further page token. The default is
`GOOGLE_TEXT_MAX_PAGES=3` to include more nearby candidates, including
stations that may appear only on a later page. Use `=1` or `=2` to reduce
request volume at the cost of potentially missing stations or lower prices.
The application validates the 1–3 range at startup. These settings apply
to both the internal REST API and WhatsApp; HERE is an alternative provider.

Three pages **do not guarantee** that Google returns a particular gas
station, including Sam's Club. Location, radius, current opening hours,
selected fuel price, Google provider coverage and the five-result display
limit can also affect whether a station appears. Price/best rankings compare
only the candidates actually fetched.

The existing per-user search rate limiter and WhatsApp message-ID
deduplicator still prevent excess provider requests. Opening hours, price
and reported price-update times come in the Places request; no per-station
details requests were added. The WhatsApp result keeps a concise distance
label and does not append a directions URL.

The project **does not cache Google Places or Routes responses**, prices or
hours to avoid stale prices/incorrect open status and restrictions on storing
Google Maps Content. A repeated, *new* search is a fresh provider request.

## Actual driving distance and ETA (opt-in)

**The Google Routes API is separately billable.** `ROUTES_API_ENABLED=false`
is the safe default: WhatsApp labels the existing geographic distance
"Approx. distance" / "Distancia aproximada". Do not mistake that estimate
for the distance you would actually drive.

When enabled, the bot sends **one** `computeRouteMatrix` HTTP request with
one origin and up to five destinations. Each origin/destination pair counts
as a **separately billable matrix element**; one HTTP call with five
destinations can cost five elements. `ROUTES_MAX_DESTINATIONS` defaults to
5 and can be reduced to 1–4 for a tighter budget, but then the other
displayed stations have no calculated driving distance. No additional Places
requests, per-station route HTTP calls, route-response caching or automatic
retries are added.

The principal WhatsApp "Distance / Distancia" figure now uses the **actual
driving route**, with a separate approximate driving time, whenever a valid
route is available. There is no second geographic distance or "Cómo llegar"
link. For a failed/unsupported route, WhatsApp says **"Driving distance
unavailable" / "Distancia por carretera no disponible"**, never quietly
displays straight-line miles under a driving-distance label.

For "Closest" and "Best", the bot reorders only the **five preselected
display candidates** that have actual driving routes, preserving the
verified-open-before-unknown-hours policy. "Best" travel-cost estimates are
recomputed with road miles for candidates with a route; ones without a
route are placed after route-verified choices within their hours category.
"Cheapest" still orders by available fuel price. The original Google/HERE
candidate search and radius use geographic distance to keep matrix billing
bounded; a station outside those five candidates will not be considered
for road ranking, and a valid road trip may exceed the selected geographic
search radius. The ETA uses `TRAFFIC_UNAWARE`, **not live traffic**.

To activate after reviewing your Google Cloud budget:

1. Enable **Routes API** for the same Google Cloud project used by the bot
   and allow the server-side API key to access it. The current Places-only
   API-key restriction may otherwise reject Routes requests.
2. Set `ROUTES_API_ENABLED=true` in Railway and leave
   `ROUTES_MAX_DESTINATIONS=5` if you want a distance for all five displayed
   stations. You can lower it to 1–4 for fewer billable matrix elements,
   accepting "distance unavailable" on the remaining stations.
3. Confirm in WhatsApp that the primary distance has changed from approximate
   to driving miles, the ETA appears, and nearby-road ordering makes sense.
   Review Google Cloud usage for both Places Text Search and Compute Route
   Matrix Essentials. Set a Routes API quota and Cloud Billing budget.
4. Set `ROUTES_API_ENABLED=false` if the added cost is unexpectedly high.
   The original search still works, showing an explicitly approximate
   geographic distance.

**Automated tests do not verify Google Cloud billing or live API quotas.**

If a Google Cloud project imposes an API quota, reaching the quota may cause
route enrichment to fail gracefully. Set separate Cloud Billing budgets and
service quotas; application-level request caps do **not** guarantee a fixed
billing amount. The bot has no access to your Google Cloud spending dashboard
and cannot independently verify the actual amount charged.

Official references:

- [Places Text Search pagination](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places/searchText)
- [Routes matrix elements and REST requests](https://developers.google.com/maps/documentation/routes/compute_route_matrix)
- [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Service-specific Maps Content storage terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)


## Production spending guard: route-matrix elements (2026-09-21)

Both the regular five-result search and the on-demand Premium favorite comparison
use `app.services.road_routes.add_road_routes`; therefore both share the **same
atomic Redis budget**. Route matrices bill by **elements, not by HTTP requests**:
one origin × five destinations reserves five elements. Production reserves all
eligible destinations *before* sending a request, counting even failed and
timed-out attempts conservatively. A Redis Lua transaction enforces:

- `ROUTES_DAILY_ELEMENT_LIMIT=25` (default initial test ceiling, UTC days).
- `ROUTES_MONTHLY_ELEMENT_LIMIT=150` (default initial test ceiling, UTC months).
- `ROUTES_MAX_DESTINATIONS=5` (maximum elements per single request).

These caps apply **in aggregate across all WhatsApp users and both search
flows**, not separately per user or per Railway worker. The key prefix is stable
across deploys and Redis counters expire at the next UTC day/month boundary.
At the cap, or if Redis is unavailable, the server skips the Routes HTTP call
and reports that driving distance is unavailable; station search still works.
The allowance is *not* a USD spending ceiling and does not count Maps/Routes
calls from other services, other API keys, or Google-side retries. It also does
not govern Places Text Search or the paid Place Details requests used by
`Comparar favoritas`. Set Google Cloud API quotas in addition to this limit.

**Routes has been turned off in Railway while these guardrails are verified.**
Before turning `ROUTES_API_ENABLED=true` again, verify the right Google Cloud
project/key, inspect existing Google Cloud Billing charges, configure a
service-specific **Routes API / Compute Route Matrix quota** in Maps Platform
→ Quotas, and configure a Cloud Billing budget with alert emails. Important:
**budget alerts are not hard spending caps**. Google Cloud quotas apply to the
whole project/service and can offer an independent brake, but Google may
present a per-minute matrix element quota rather than an editable daily
product quota; in that case restrict the supported quota and use this app's
daily/monthly Redis limits. The app alone cannot guarantee a fixed bill.

The numeric 25/day and 150/month values are **conservative testing defaults**,
not an assumption about a personal spending budget or a recommendation for a
future public service. Change them after comparing current usage, current
Google Maps SKU/pricing, actual Cloud Billing reports and available quota
controls. Reducing these values takes effect immediately against already
reserved elements. Do not reset or rename the Redis budget keys to sidestep
a quota. Confirm deployment and API quota settings before re-enabling Routes.
