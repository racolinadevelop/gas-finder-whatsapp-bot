# Google API cost controls and road routes

## Current server-side API request budget

Each actual gas-station search uses **one to two** Google Places Text
Search requests by default (up to 20 candidates per page). The provider
stops earlier if there is no further page token. Set
`GOOGLE_TEXT_MAX_PAGES=1` for a stricter one-request cap or `=3` to restore
the old, more exhaustive three-page behavior. The upper bound is validated
at application startup. The same settings apply to the internal REST API and
WhatsApp. A separate HERE provider is available.

Fewer pages can omit gas stations on later pages, including cheaper stations
such as Sam's Club in some searches; price/best rankings compare only the
candidates that were actually fetched. Do not advertise page-one results as
the globally cheapest. If results are sparse or a known station is missing,
try `GOOGLE_TEXT_MAX_PAGES=3` temporarily and compare results at the same
location. This change intentionally trades search breadth for request cost.

The existing per-user search rate limiter and WhatsApp message-ID
deduplicator still prevent excess provider requests. Opening hours and fuel
prices come in the Places request; no per-station details requests were added.

The project **does not cache Google Places or Routes responses**, prices or
hours to avoid stale prices/incorrect open status and restrictions on storing
Google Maps Content. A repeated, *new* search is a fresh provider request.
Google Maps Directions URLs appended to WhatsApp results do not call the
project's server-side Google APIs and need no API key.

## Optional road distance and ETA

`ROUTES_API_ENABLED=false` is the safe default: Places search and Google Maps
direction links work, but only straight-line miles are shown in the bot.
When road routes are enabled, `app/services/road_routes.py` sends **one
Google Routes `computeRouteMatrix` HTTP request** after fetching the top
stations, with **one origin and at most
`ROUTES_MAX_DESTINATIONS` destinations** (default 5, valid 1–5). It requests
driving distance and approximate time using `TRAFFIC_UNAWARE`; this is not
live-traffic ETA. A matrix request is billed in **elements**, so five
destinations can count as five billable elements even though it is one HTTP
request. The API may also bill a failed request according to its policies.

The road distance/ETA are supplementary to the existing station ranking,
straight-line search radius and best-option estimated cost. The bot labels
straight-line distance explicitly and shows road distance only when Google
returned a valid route. An unavailable Routes API, partial matrix error or
invalid element must leave the previous search/results intact. It does not
trigger an additional search or retry request. A displayed route can exceed
the selected straight-line radius. Directions opened by the user in Google
Maps may use a different live route and ETA.

To activate after reviewing your Google Cloud budget:

1. Enable **Routes API** in the same Google Cloud project as the Places
   key. Ensure the server-side API key is allowed to use both APIs.
2. Set `ROUTES_API_ENABLED=true` in Railway and optionally
   `ROUTES_MAX_DESTINATIONS=3` to calculate routes only for the first three
   displayed stations. The others still have labeled straight-line distance
   and a directions link.
3. Test a location in WhatsApp, confirm route miles and ETA appear and
   compare Google Cloud Maps Platform billing for **Text Search** and
   **Compute Route Matrix Essentials** before increasing traffic.
4. Set `ROUTES_API_ENABLED=false` immediately if the added cost is
   unexpectedly high; the existing search still works.

If a Google Cloud project imposes an API quota, reaching the quota may cause
route enrichment to fail gracefully. Set separate Cloud Billing budgets and
service quotas; application-level request caps do **not** guarantee a fixed
billing amount. The bot has no access to your Google Cloud spending dashboard
and cannot independently verify the actual amount charged.

Official references:

- [Places Text Search pagination](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places/searchText)
- [Routes matrix elements and REST requests](https://developers.google.com/maps/documentation/routes/compute_route_matrix)
- [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started)
- [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Service-specific Maps Content storage terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)
