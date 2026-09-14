import httpx

from app.config import GOOGLE_MAPS_API_KEY
from app.utils.distance import calculate_distance_miles

GOOGLE_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"


class GooglePlacesServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def search_nearby_gas_stations(latitude: float, longitude: float, radius: float = 5000):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.location"
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
        }

        stations.append(station)

    stations.sort(key=lambda station: station["distance_miles"])

    return {
        "stations": stations,
        "count": len(stations),
        "message": (
            "Gas stations found." if stations else "No valid gas stations found."
        ),
    }
