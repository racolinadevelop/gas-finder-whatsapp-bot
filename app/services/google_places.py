import logging

import httpx

from app.config import GOOGLE_MAPS_API_KEY
from app.providers import GasStationProviderError
from app.utils.distance import calculate_distance_miles
from app.utils.cost import calculate_estimated_cost

logger = logging.getLogger(__name__)

GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_CANDIDATE_LIMIT = 20
GOOGLE_TEXT_PAGE_SIZE = 20
GOOGLE_TEXT_MAX_PAGES = 3
METERS_PER_MILE = 1609.344


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


def parse_open_now(place: dict) -> bool | None:
    """Only a current, explicit Google boolean proves open/closed."""
    open_now = (place.get("currentOpeningHours") or {}).get("openNow")
    return open_now if isinstance(open_now, bool) else None


def _open_priority(station: dict) -> int:
    # Unknown hours are not confirmed open; retain them only as fallback.
    return 0 if station.get("open_now") is True else 1


def sort_stations(stations: list, sort: str) -> list:
    if sort == "price":
        stations.sort(
            key=lambda station: (
                _open_priority(station),
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
                _open_priority(station),
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
        stations.sort(
            key=lambda station: (_open_priority(station), station["distance_miles"])
        )

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

    if _open_priority(candidate) != _open_priority(current):
        return _open_priority(candidate) < _open_priority(current)

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


def _log_search_summary(
    *,
    pages: int,
    candidates: int,
    within_radius: int,
    priced: int,
    results: int,
    fuel_type: str,
    sort: str,
) -> None:
    logger.info(
        (
            "Google Places search pages=%s candidates=%s "
            "within_radius=%s priced=%s results=%s fuel=%s sort=%s"
        ),
        pages,
        candidates,
        within_radius,
        priced,
        results,
        fuel_type,
        sort,
    )


def _request_google_text_search_page(headers: dict, payload: dict) -> dict:
    try:
        response = httpx.post(
            GOOGLE_PLACES_TEXT_SEARCH_URL,
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
        return response.json()
    except ValueError as exc:
        raise GooglePlacesServiceError(
            "Google Places returned an invalid response.",
            status_code=502,
        ) from exc


def _fetch_google_text_search_places(
    *,
    headers: dict,
    latitude: float,
    longitude: float,
    radius: float,
) -> tuple[list, int]:
    base_payload = {
        "textQuery": "gas station",
        "includedType": "gas_station",
        "strictTypeFiltering": True,
        "pageSize": GOOGLE_TEXT_PAGE_SIZE,
        # Kept during the migration so older tests/instrumentation that inspect
        # this field remain compatible. Text Search uses pageSize in preference
        # to this deprecated field.
        "maxResultCount": GOOGLE_CANDIDATE_LIMIT,
        "rankPreference": "DISTANCE",
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius,
            }
        },
    }

    places = []
    page_token = None
    pages_fetched = 0

    for _ in range(GOOGLE_TEXT_MAX_PAGES):
        payload = dict(base_payload)
        if page_token:
            payload["pageToken"] = page_token

        data = _request_google_text_search_page(headers, payload)
        pages_fetched += 1
        places.extend(data.get("places", []))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return places, pages_fetched


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
            "places.fuelOptions,"
            "places.businessStatus,"
            "places.currentOpeningHours,"
            "nextPageToken"
        ),
    }

    places, pages_fetched = _fetch_google_text_search_places(
        headers=headers,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
    )

    if not places:
        _log_search_summary(
            pages=pages_fetched,
            candidates=0,
            within_radius=0,
            priced=0,
            results=0,
            fuel_type=fuel_type,
            sort=sort,
        )
        return {
            "stations": [],
            "count": 0,
            "message": "No gas stations found in the selected area.",
        }

    stations = []
    radius_miles = radius / METERS_PER_MILE

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

        # Text Search uses a location bias rather than a strict circular
        # restriction, so enforce the requested search radius ourselves.
        if distance_miles > radius_miles:
            continue

        # Google may return closed stations with old fuel prices. Exclude
        # only an explicit current-hour closed status or a non-operational
        # business status; missing hours remain available but labelled.
        if place.get("businessStatus") in {
            "CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY", "FUTURE_OPENING"
        }:
            continue
        open_now = parse_open_now(place)
        if open_now is False:
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
            "open_now": open_now,
            "fuel_prices": parsed_fuel_prices,
            "selected_fuel": selected_fuel,
            "estimated_cost": estimated_cost,
        }

        stations.append(station)

    within_radius_count = len(stations)
    stations = deduplicate_stations(stations)
    stations = [
        station for station in stations if station["selected_fuel"]["available"]
    ]
    priced_count = len(stations)
    stations = sort_stations(stations, sort)[:limit]

    _log_search_summary(
        pages=pages_fetched,
        candidates=len(places),
        within_radius=within_radius_count,
        priced=priced_count,
        results=len(stations),
        fuel_type=fuel_type,
        sort=sort,
    )

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
