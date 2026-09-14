import httpx

from app.config import GOOGLE_MAPS_API_KEY


GOOGLE_PLACES_NEARBY_URL = (
    "https://places.googleapis.com/v1/places:searchNearby"
)


def search_nearby_gas_stations(
    latitude: float,
    longitude: float,
    radius: float = 5000
):
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

    response = httpx.post(
        GOOGLE_PLACES_NEARBY_URL,
        headers=headers,
        json=payload,
        timeout=10.0,
    )

    response.raise_for_status()

    return response.json()