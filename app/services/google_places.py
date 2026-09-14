import httpx

from app.config import GOOGLE_MAPS_API_KEY
from app.utils.distance import calculate_distance_miles

GOOGLE_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"


class GooglePlacesServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def parse_fuel_prices(fuel_prices: list) -> dict:
    parsed_prices = {}

    for fuel in fuel_prices:
        fuel_type = fuel.get("type")
        price_data = fuel.get("price", {})

        units = int(price_data.get("units", 0))
        nanos = int(price_data.get("nanos", 0))

        price = units + (nanos / 1_000_000_000)

        parsed_prices[fuel_type] = {
            "price": round(price, 3),
            "currency": price_data.get("currencyCode", "USD"),
            "updated_at": fuel.get("updateTime"),
        }

    return parsed_prices


FUEL_TYPE_MAP = {
    "regular": "REGULAR_UNLEADED",
    "premium": "PREMIUM",
    "diesel": "DIESEL",
}


def sort_stations(stations: list, sort: str) -> list:
    if sort == "price":
        stations.sort(
            key=lambda station: (
                not station["selected_fuel"]["available"],
                (
                    station["selected_fuel"]["price"]
                    if station["selected_fuel"]["available"]
                    else float("inf")
                ),
                station["distance_miles"],
            )
        )
    else:
        stations.sort(key=lambda station: station["distance_miles"])

    return stations


def search_nearby_gas_stations(
    latitude: float,
    longitude: float,
    radius: float = 5000,
    fuel_type: str = "regular",
    sort: str = "distance",
):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.location,"
            "places.fuelOptions"
        ),
    }

    payload = {
        "includedTypes": ["gas_station"],
        "maxResultCount": 5,
        "rankPreference": "DISTANCE",
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius,
            }
        },
    }

    try:
        response = httpx.post(
            GOOGLE_PLACES_NEARBY_URL,
            headers=headers,
            json=payload,
            timeout=10.0,
        )

        response.raise_for_status()

    except httpx.TimeoutException as exc:
        raise GooglePlacesServiceError(
            "Google Places took too long to respond.",
            status_code=504,
        ) from exc

    except httpx.HTTPStatusError as exc:
        google_status = exc.response.status_code

        if google_status == 429:
            raise GooglePlacesServiceError(
                "Google Places request limit has been reached.",
                status_code=503,
            ) from exc

        if google_status in (401, 403):
            raise GooglePlacesServiceError(
                "Google Places authentication or permission error.",
                status_code=502,
            ) from exc

        if google_status >= 500:
            raise GooglePlacesServiceError(
                "Google Places is temporarily unavailable.",
                status_code=503,
            ) from exc

        raise GooglePlacesServiceError(
            "Google Places request failed.",
            status_code=502,
        ) from exc

    except httpx.RequestError as exc:
        raise GooglePlacesServiceError(
            "Unable to connect to Google Places.",
            status_code=502,
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise GooglePlacesServiceError(
            "Google Places returned an invalid response.",
            status_code=502,
        ) from exc

    places = data.get("places", [])

    if not places:
        return {
            "stations": [],
            "count": 0,
            "message": "No gas stations found in the selected area.",
        }

    stations = []

    for place in places:
        location = place.get("location", {})

        station_latitude = location.get("latitude")
        station_longitude = location.get("longitude")

        if station_latitude is None or station_longitude is None:
            continue

        display_name = place.get("displayName", {})

        station_name = display_name.get("text", "Unknown gas station")

        station_address = place.get("formattedAddress", "Address not available")

        fuel_options = place.get("fuelOptions", {})
        fuel_prices = fuel_options.get("fuelPrices", [])
        parsed_fuel_prices = parse_fuel_prices(fuel_prices)

        google_fuel_type = FUEL_TYPE_MAP[fuel_type]

        fuel_data = parsed_fuel_prices.get(google_fuel_type)

        if fuel_data:
            selected_fuel = {
                "available": True,
                **fuel_data,
            }
        else:
            selected_fuel = {
                "available": False,
                "price": None,
                "currency": None,
                "updated_at": None,
            }

        station = {
            "id": place.get("id"),
            "name": station_name,
            "address": station_address,
            "latitude": station_latitude,
            "longitude": station_longitude,
            "distance_miles": calculate_distance_miles(
                latitude,
                longitude,
                station_latitude,
                station_longitude,
            ),
            "fuel_prices": parsed_fuel_prices,
            "selected_fuel": selected_fuel,
        }

        stations.append(station)

    stations = sort_stations(stations, sort)

    return {
        "stations": stations,
        "count": len(stations),
        "message": (
            "Gas stations found." if stations else "No valid gas stations found."
        ),
    }
