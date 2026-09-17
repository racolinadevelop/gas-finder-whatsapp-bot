# Gas-station data providers

The application supports two interchangeable providers:

- `google`: Google Places API (New), the default.
- `here`: HERE Fuel Prices API v3.

Both adapters return the same internal station structure, so the API and
WhatsApp conversation do not depend on a specific provider.

## Google behavior

Google Nearby Search ranks the candidate response by distance. The application
requests the maximum 20 candidates, then performs these steps locally:

1. Parse the price for the selected fuel.
2. Merge duplicate results at the same normalized address.
3. Remove stations without an available price.
4. Sort by distance, price, or estimated best cost.
5. Return only the requested display limit.

This prevents the five closest Google records from becoming the complete
search universe before price sorting.

## HERE test configuration

Set the provider and API key locally or in Railway:

```env
GAS_STATION_PROVIDER=here
HERE_API_KEY=your_here_api_key
```

The HERE adapter requests the selected fuel type, excludes stations with
unknown prices, evaluates up to 50 candidates, normalizes the response, and
then applies the same application sorting and display limit.

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
