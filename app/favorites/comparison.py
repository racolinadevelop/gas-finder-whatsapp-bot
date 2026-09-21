"""On-demand Premium comparison of up to five saved Google Places.

One Place Details request per saved Google place ID (no Text Search), plus
at most one existing Routes matrix call when the separately configured
Routes feature is enabled. Never cache location, provider responses or prices.
"""

import logging
import re
from collections.abc import Callable

import httpx

from app.config import GOOGLE_MAPS_API_KEY, ROUTES_API_ENABLED
from app.favorites.models import FavoriteStation
from app.services.google_places import FUEL_TYPE_MAP, parse_fuel_prices, parse_open_now
from app.services.road_routes import add_road_routes
from app.presentation.price_freshness import price_update_lines

logger = logging.getLogger(__name__)
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/"
PLACE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{5,150}\Z")
DETAILS_FIELD_MASK = (
    "id,location,fuelOptions,businessStatus,currentOpeningHours"
)
MAX_COMPARED_FAVORITES = 5


def fetch_saved_place_details(
    place_id: str, *, api_key: str = GOOGLE_MAPS_API_KEY
) -> dict | None:
    """Return requested fields only; skip failed/outdated Place IDs."""
    if not api_key or not PLACE_ID_PATTERN.fullmatch(place_id):
        return None
    try:
        response = httpx.get(
            PLACE_DETAILS_URL + place_id,
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": DETAILS_FIELD_MASK,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("id") != place_id:
            return None
        return data
    except (httpx.HTTPError, ValueError, TypeError):
        # Do not log place ID, location, credentials or provider response body.
        logger.warning("A favorite station's Place Details are unavailable")
        return None


def compare_saved_places(
    favorites: tuple[FavoriteStation, ...],
    *,
    latitude: float,
    longitude: float,
    fuel_type: str,
    fetch_details: Callable[[str], dict | None] = fetch_saved_place_details,
    routes_enabled: bool = ROUTES_API_ENABLED,
    enrich_routes: Callable[..., dict] = add_road_routes,
) -> dict:
    """Refresh ONLY the selected five saved stations; missing price sorts last."""
    if fuel_type not in FUEL_TYPE_MAP:
        raise ValueError("Unsupported fuel type")
    if not 1 <= len(favorites) <= MAX_COMPARED_FAVORITES:
        raise ValueError("Compare between one and five favorites")

    stations = []
    for favorite in favorites:
        place_id = favorite.key.removeprefix("place:")
        place = (
            fetch_details(place_id)
            if favorite.key.startswith("place:")
            and PLACE_ID_PATTERN.fullmatch(place_id)
            else None
        )
        details_available = place is not None
        if place and place.get("businessStatus") in {
            "CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY", "FUTURE_OPENING"
        }:
            open_now = False
        else:
            open_now = parse_open_now(place or {})
        location = (place or {}).get("location") or {}
        lat, lng = location.get("latitude"), location.get("longitude")
        valid_location = (
            isinstance(lat, (int, float)) and not isinstance(lat, bool)
            and isinstance(lng, (int, float)) and not isinstance(lng, bool)
            and -90 <= lat <= 90 and -180 <= lng <= 180
        )
        # Missing/invalid price objects must not turn into a fabricated $0.
        raw_fuels = ((place or {}).get("fuelOptions") or {}).get("fuelPrices") or []
        valid_fuels = [
            item for item in raw_fuels
            if isinstance(item, dict)
            and isinstance(item.get("price"), dict)
            and isinstance(item["price"].get("units"), int)
            and not isinstance(item["price"]["units"], bool)
            and isinstance(item["price"].get("nanos", 0), int)
            and item["price"].get("currencyCode") == "USD"
        ]
        fuel_prices = parse_fuel_prices(valid_fuels)
        selected = fuel_prices.get(FUEL_TYPE_MAP[fuel_type]) or {}
        price = selected.get("price")
        if price is not None and price <= 0:
            price = None
        # No old saved price is used as a fallback after a failed refresh.
        stations.append({
            "name": favorite.name,
            "address": favorite.address,
            "open_now": open_now,
            "details_available": details_available,
            "latitude": lat if valid_location else None,
            "longitude": lng if valid_location else None,
            "selected_fuel": {
                "price": price,
                "updated_at": selected.get("updated_at"),
                "currency": selected.get("currency"),
            },
        })

    result = {"stations": stations}
    if routes_enabled and any(
        item["latitude"] is not None and item["open_now"] is not False
        for item in stations
    ):
        # Route enrichment is capped to <=5 destinations by this comparison.
        # A closed station is intentionally excluded from the matrix.
        eligible = [
            item for item in stations
            if item["latitude"] is not None and item["open_now"] is not False
        ]
        routed = enrich_routes(
            {"stations": eligible}, latitude=latitude, longitude=longitude,
        )
        by_id = {
            (item["latitude"], item["longitude"]): item
            for item in routed.get("stations", [])
        }
        for item in stations:
            route = by_id.get((item["latitude"], item["longitude"]))
            if route is not None:
                item.update({
                    key: route[key] for key in (
                        "road_distance_miles", "road_eta_minutes",
                    ) if key in route
                })

    stations.sort(key=lambda item: (
        item["open_now"] is False,
        item["selected_fuel"]["price"] is None,
        item["selected_fuel"]["price"]
        if item["selected_fuel"]["price"] is not None else float("inf"),
        item.get("road_distance_miles", float("inf")),
        item["name"].casefold(),
    ))
    return {"stations": stations, "fuel_type": fuel_type}


def format_favorite_comparison(result: dict, language: str) -> str:
    """Show provider-reported prices honestly; road distance only when routed."""
    es = language == "es"
    fuel = {
        "es": {"regular": "Regular", "premium": "Premium", "diesel": "Diésel"},
        "en": {"regular": "Regular", "premium": "Premium", "diesel": "Diesel"},
    }["es" if es else "en"][result["fuel_type"]]
    lines = [
        f"⭐ Comparación de favoritas · {fuel}"
        if es else f"⭐ Favorite station comparison · {fuel}"
    ]
    for index, station in enumerate(result["stations"], 1):
        selected = station["selected_fuel"]
        price = selected["price"]
        if station["open_now"] is False:
            price_label = "Cerrada" if es else "Closed"
        elif price is None or selected["currency"] != "USD":
            price_label = "Precio no disponible" if es else "Price unavailable"
        else:
            price_label = f"${price:.3f}/gal"
        lines.append(f"\n{index}. {station['name']}\n⛽ {price_label}")
        if station.get("road_distance_miles") is not None:
            lines.append(
                f"🚗 {station['road_distance_miles']:.2f} mi · "
                f"{station['road_eta_minutes']} min"
            )
        else:
            lines.append(
                "🚗 Ruta por carretera no disponible"
                if es else "🚗 Driving route unavailable"
            )
        if price is not None and station["open_now"] is not False:
            lines.extend(price_update_lines(selected.get("updated_at"), language=language))
        if not station["details_available"]:
            lines.append(
                "Datos de esta estación no disponibles por ahora."
                if es else "Station information is temporarily unavailable."
            )
        if station["address"]:
            lines.append(f"📍 {station['address']}")
    lines.append(
        "\nPrecios reportados por Google; pueden diferir en el surtidor."
        if es else
        "\nPrices reported by Google may differ at the pump."
    )
    return "\n".join(lines)
