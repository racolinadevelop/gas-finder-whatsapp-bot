# Gas-station data providers

The application supports two interchangeable providers:

- `google`: Google Places API (New), the default.
- `here`: HERE Fuel Prices API v3.

Both adapters return the same internal station structure, so the API and
WhatsApp conversation do not depend on a specific provider.

## Google behavior

Google Places Text Search requests gas-station candidates near the supplied
location. The application requests up to two pages of up to 20 candidates
each by default (`GOOGLE_TEXT_MAX_PAGES` can be 1–3) and applies the
requested radius locally (Text Search's location bias is not a strict
geographic filter). Fewer pages save requests but may omit later, cheaper
candidates, including some Sam's Club results. It then:

1. Excludes businesses Google explicitly marks non-operational and stations
   whose current opening-hours response explicitly says `openNow=false`.
2. Keeps stations with unknown hours as fallback results labeled as unverified;
   do not interpret unknown as confirmed open.
3. Parses the price for the selected fuel and merges duplicate addresses.
4. Excludes stations without an available price for that fuel.
5. Sorts verified-open stations before unknown-hours fallbacks, then by the
   chosen distance, price or estimated-cost criterion.
6. Returns up to the requested display limit.

Price data and operating-hours responses come from the provider, can be missing
or stale, and are not independently verified by this application. This policy
also applies to Sam's Club and other brands; there is no brand-specific filter.

## HERE test configuration

Set the provider and API key locally or in Railway:

```env
GAS_STATION_PROVIDER=here
HERE_API_KEY=your_here_api_key
```

The HERE adapter requests the selected fuel type, excludes stations with
unknown prices, evaluates up to 50 candidates, normalizes the response, and
then applies application sorting and display limit. HERE does not currently
supply verified real-time operating hours to the bot, so its station hours
are shown as unknown rather than confirmed open.

## Louisville comparison checklist

Before changing the production provider, run Google and HERE separately using
the same inputs:

- The exact WhatsApp location used in the reported search.
- A 10-mile radius.
- Regular fuel.
- Cheapest-price sorting.
- The same date and approximate time.

Record for each provider:

- Whether Sam's Club appears.
- Its displayed price and last-update time.
- The number of stations with prices.
- Duplicate addresses, if any.
- Prices that disagree with the station sign or receipt.

Do not enable HERE in production until its Louisville coverage and units have
been verified with a real API key. Provider data can still be incomplete or
stale even when the location search itself is accurate.

See [API Costs and Routes](API_COSTS_AND_ROUTES.md) for billing tradeoffs,
optional driving-route enrichment and Google Cloud activation.
