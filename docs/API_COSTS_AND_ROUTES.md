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

**This code cannot activate Routes API or change your Railway variables
without access to those accounts.** A green automated test does not prove
Routes is enabled or paid traffic can successfully use the live API.

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
