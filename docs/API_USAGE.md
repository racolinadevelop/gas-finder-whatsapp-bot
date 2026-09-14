# API Usage

This document explains how to use the Gas Finder REST API.

## Base URL

When running the project locally:

```text
http://127.0.0.1:8000
```

Swagger documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Health Check

### Request

```http
GET /
```

### Response

```json
{
  "message": "Gas Finder API is running"
}
```

---

## Find Nearby Gas Stations

### Endpoint

```http
GET /api/v1/gas-stations/nearby
```

This endpoint searches for nearby gas stations using latitude and longitude.

## Query Parameters

### latitude

Required.

Valid range:

```text
-90 to 90
```

Example:

```text
38.2527
```

### longitude

Required.

Valid range:

```text
-180 to 180
```

Example:

```text
-85.7585
```

### radius

Optional.

Search radius in meters.

Default:

```text
5000
```

Maximum:

```text
50000
```

Example:

```text
5000
```

### fuel_type

Optional.

Supported values:

```text
regular
premium
diesel
```

Default:

```text
regular
```

### sort

Optional.

Supported values:

```text
distance
price
best
```

Default:

```text
distance
```

#### distance

Returns the closest stations first.

#### price

Returns stations with the lowest available fuel price first.

Stations without price information are placed at the end.

#### best

Uses both fuel price and estimated travel cost to determine the best option.

Stations without price information are placed at the end.

### limit

Optional.

Number of gas stations to request.

Valid range:

```text
1 to 20
```

Default:

```text
10
```

### gallons_needed

Optional.

Estimated number of gallons the user plans to purchase.

Default:

```text
10
```

Used only for the estimated cost calculation.

### vehicle_mpg

Optional.

Approximate fuel efficiency of the vehicle in miles per gallon.

Default:

```text
25
```

Used only for the estimated cost calculation.

---

## Example Request

```http
GET /api/v1/gas-stations/nearby?latitude=38.2527&longitude=-85.7585&radius=5000&fuel_type=regular&sort=price&limit=10
```

## Example Response

```json
{
  "stations": [
    {
      "id": "example-place-id",
      "name": "Example Gas Station",
      "address": "123 Example Street",
      "latitude": 38.25,
      "longitude": -85.75,
      "distance_miles": 0.8,
      "fuel_prices": {
        "REGULAR_UNLEADED": {
          "price": 2.999,
          "currency": "USD",
          "updated_at": "2026-09-13T20:00:00Z"
        }
      },
      "selected_fuel": {
        "available": true,
        "price": 2.999,
        "currency": "USD",
        "updated_at": "2026-09-13T20:00:00Z"
      },
      "estimated_cost": {
        "fuel_purchase_cost": 29.99,
        "travel_cost": 0.19,
        "estimated_total_cost": 30.18
      }
    }
  ],
  "count": 1,
  "message": "Gas stations found."
}
```

---

## When Fuel Price Is Not Available

Some gas stations do not have fuel price data available through Google Places.

The API returns:

```json
{
  "selected_fuel": {
    "available": false,
    "price": null,
    "currency": null,
    "updated_at": null
  },
  "estimated_cost": null
}
```

This is not considered an API error.

---

## No Gas Stations Found

If no gas stations are found in the selected area:

```json
{
  "stations": [],
  "count": 0,
  "message": "No gas stations found in the selected area."
}
```

---

## Validation Errors

Invalid query parameters are rejected automatically by FastAPI.

Example:

```text
latitude = 200
```

The valid latitude range is:

```text
-90 to 90
```

FastAPI returns:

```text
HTTP 422
```

Other examples that return validation errors include:

```text
radius <= 0
radius > 50000
limit < 1
limit > 20
unsupported fuel_type
unsupported sort option
```

---

## External Service Errors

The API handles common Google Places failures.

Possible responses include:

```text
502 - Google Places authentication or connection problem
503 - Google Places unavailable or request limit reached
504 - Google Places timeout
```

Example:

```json
{
  "detail": "Google Places is temporarily unavailable."
}
```

---

## Best Option Calculation

The `best` sort mode estimates the total cost of using each station.

The calculation considers:

- fuel price
- distance to the station
- round-trip distance
- gallons needed
- vehicle MPG

Example:

```text
Station A
Fuel price: $2.90
Distance: 8 miles

Station B
Fuel price: $2.95
Distance: 1 mile
```

Station B may be considered the better option because the extra travel required for Station A can cost more than the savings at the pump.

Important:

The current MVP uses straight-line distance between coordinates.

It does not yet calculate actual driving distance.

A future version may use a routing service for more accurate travel cost calculations.

---

## Running Automated Tests

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Run the tests with:

```bash
python -m pytest -v
```

The project includes automated tests for:

- invalid coordinates
- invalid result limits
- empty results
- Google Places timeout
- authentication errors
- rate limits
- server errors
- connection errors
- sorting by distance
- sorting by price
- same-price distance tie breaking
- best-option calculation