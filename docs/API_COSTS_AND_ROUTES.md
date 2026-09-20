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

## Optional road distance and ETA

`ROUTES_API_ENABLED=false` is the safe default: Places search works and
only geographic distance is shown in the bot.
When road routes are enabled, `app/services/road_routes.py` sends **one
Google Routes `computeRouteMatrix` HTTP request** after fetching the top
stations, with **one origin and at most
`ROUTES_MAX_DESTINATIONS` destinations** (default 5, valid 1–5). It requests
driving distance and approximate time using `TRAFFIC_UNAWARE`; this is not
live-traffic ETA. A matrix request is billed in **elements**, so five
destinations can count as five billable elements even though it is one HTTP
request. The API may also bill a failed request according to its policies.

The road distance/ETA are supplementary to the existing station ranking,
geographic search radius and best-option estimated cost. WhatsApp keeps its
concise distance label and shows road distance only when Google returned a
valid route. An unavailable Routes API, partial matrix error or invalid
element leaves the existing search/results intact. It does not trigger an
additional search or retry request. A displayed route can exceed the
selected geographic radius.

To activate after reviewing your Google Cloud budget:

1. Enable **Routes API** in the same Google Cloud project as the Places
   key. Ensure the server-side API key is allowed to use both APIs.
2. Set `ROUTES_API_ENABLED=true` in Railway and optionally
   `ROUTES_MAX_DESTINATIONS=3` to calculate routes only for the first three
   displayed stations. The others retain their ordinary distance label.
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
- [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Service-specific Maps Content storage terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)
