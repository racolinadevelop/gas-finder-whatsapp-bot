import httpx

from app.config import GOOGLE_MAPS_API_KEY
from app.providers import GasStationProviderError
from app.utils.distance import calculate_distance_miles
from app.utils.cost import calculate_estimated_cost

GOOGLE_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
GOOGLE_CANDIDATE_LIMIT = 20


class GooglePlacesServiceError(GasStationProviderError):
    pass


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

    elif sort == "best":
        stations.sort(
            key=lambda station: (
                station["estimated_cost"] is None,
                (
                    station["estimated_cost"]["estimated_total_cost"]
                    if station["estimated_cost"]
                    else float("inf")
                ),
                station["distance_miles"],
            )
        )

    else:
        stations.sort(key=lambda station: station["distance_miles"])

    return stations


def _station_identity(station: dict) -> tuple:
    address = " ".join(station.get("address", "").lower().split())

    if address and address != "address not available":
        return ("address", address)

    return (
        "location",
        round(station["latitude"], 4),
        round(station["longitude"], 4),
    )


def _prefer_station(candidate: dict, current: dict) -> bool:
    candidate_fuel = candidate["selected_fuel"]
    current_fuel = current["selected_fuel"]

    if candidate_fuel["available"] != current_fuel["available"]:
        return candidate_fuel["available"]

    return (candidate_fuel.get("updated_at") or "") > (
        current_fuel.get("updated_at") or ""
    )


def deduplicate_stations(stations: list) -> list:
    unique_stations = {}

    for station in stations:
        identity = _station_identity(station)
        current = unique_stations.get(identity)

        if current is None or _prefer_station(station, current):
            unique_stations[identity] = station

    return list(unique_stations.values())


def _candidate_diagnostic_lines(
    stations: list,
    *,
    fuel_type: str,
    raw_candidate_count: int,
) -> list[str]:
    lines = [
        (
            "[GooglePlaces diagnostics] "
            f"raw_candidates={raw_candidate_count} "
            f"parsed_candidates={len(stations)} fuel={fuel_type}"
        )
    ]

    for index, station in enumerate(stations, start=1):
        selected_fuel = station["selected_fuel"]
        available = selected_fuel["available"]
        price = selected_fuel.get("price")
        status = "KEEP" if available else "REMOVED_NO_PRICE"
        distance = station.get("distance_miles")
        distance_text = f"{distance:.2f}mi" if distance is not None else "unknown"

        lines.append(
            (
                f"[GooglePlaces diagnostics] {index:02d}. "
                f"{station.get('name', 'Unknown gas station')} | "
                f"price={price} | status={status} | "
                f"distance={distance_text} | "
                f"address={station.get('address', 'Address not available')}"
            )
        )

    return lines


def _log_candidate_diagnostics(
    stations: list,
    *,
    fuel_type: str,
    raw_candidate_count: int,
) -> None:
    for line in _candidate_diagnostic_lines(
        stations,
        fuel_type=fuel_type,
        raw_candidate_count=raw_candidate_count,
    ):
        print(line, flush=True)


def _search_nearby_gas_stations(
    latitude: float,
    longitude: float,
    radius: float = 5000,
    fuel_type: str = "regular",
    sort: str = "distance",
    limit: int = 10,
    gallons_needed: float = 10,
    vehicle_mpg: float = 25,
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
        # Google ranks this candidate set by distance. We deliberately request
        # the maximum allowed number and only apply the user-facing limit after
        # filtering, deduplication and our own price/best sorting.
        "maxResultCount": GOOGLE_CANDIDATE_LIMIT,
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
        print(
            (
                "[GooglePlaces diagnostics] raw_candidates=0 "
                f"parsed_candidates=0 fuel={fuel_type}"
            ),
            flush=True,
        )
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

        distance_miles = calculate_distance_miles(
            latitude,
            longitude,
            station_latitude,
            station_longitude,
        )

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
        estimated_cost = None

        if selected_fuel["available"]:
            estimated_cost = calculate_estimated_cost(
                price_per_gallon=selected_fuel["price"],
                distance_miles=distance_miles,
                gallons_needed=gallons_needed,
                vehicle_mpg=vehicle_mpg,
            )

        station = {
            "id": place.get("id"),
            "name": station_name,
            "address": station_address,
            "latitude": station_latitude,
            "longitude": station_longitude,
            "distance_miles": distance_miles,
            "fuel_prices": parsed_fuel_prices,
            "selected_fuel": selected_fuel,
            "estimated_cost": estimated_cost,
        }

        stations.append(station)

    _log_candidate_diagnostics(
        stations,
        fuel_type=fuel_type,
        raw_candidate_count=len(places),
    )

    stations = deduplicate_stations(stations)
    stations = [
        station for station in stations if station["selected_fuel"]["available"]
    ]
    stations = sort_stations(stations, sort)[:limit]

    return {
        "stations": stations,
        "count": len(stations),
        "message": (
            "Gas stations found." if stations else "No valid gas stations found."
        ),
    }


class GooglePlacesProvider:
    """Provider adapter that preserves the current Google implementation."""

    def search_nearby(self, **kwargs) -> dict:
        return _search_nearby_gas_stations(**kwargs)


def search_nearby_gas_stations(**kwargs) -> dict:
    """Compatibility entry point used by the API and WhatsApp handlers."""

    return GooglePlacesProvider().search_nearby(**kwargs)
