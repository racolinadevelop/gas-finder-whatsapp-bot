"""Optional, capped Google Routes matrix enrichment for displayed stations.

Only the selected stations are sent to Routes. Matrix results are supplementary:
the existing straight-line ranking and best-option calculation remain unchanged.
No route/Places responses are persisted or cached.
"""

import logging
import math

import httpx

from app.config import GOOGLE_MAPS_API_KEY, ROUTES_MAX_DESTINATIONS

logger = logging.getLogger(__name__)
ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
METERS_PER_MILE = 1609.344


def _waypoint(latitude: float, longitude: float) -> dict:
    return {
        "waypoint": {
            "location": {
                "latLng": {"latitude": latitude, "longitude": longitude},
            },
        },
    }


def add_road_routes(
    result: dict,
    *,
    latitude: float,
    longitude: float,
    api_key: str | None = GOOGLE_MAPS_API_KEY,
    max_destinations: int = ROUTES_MAX_DESTINATIONS,
) -> dict:
    """Add real driving miles and ETA to available results with ONE HTTP call.

    Up to max_destinations matrix elements are billed independently. If Routes
    is unavailable or gives incomplete data, keep the original stations and
    straight-line distances instead of reporting fabricated road distances.
    """
    stations = result.get("stations", [])
    if not stations or not api_key:
        return result

    eligible = [
        (index, station)
        for index, station in enumerate(stations)
        if station.get("latitude") is not None
        and station.get("longitude") is not None
    ][:max_destinations]
    if not eligible:
        return result

    payload = {
        "origins": [_waypoint(latitude, longitude)],
        "destinations": [
            _waypoint(station["latitude"], station["longitude"])
            for _, station in eligible
        ],
        "travelMode": "DRIVE",
        # No live-traffic billing tier; duration is an approximate driving ETA.
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    try:
        response = httpx.post(
            ROUTE_MATRIX_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": (
                    "originIndex,destinationIndex,status,condition,"
                    "distanceMeters,duration"
                ),
            },
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        elements = response.json()
        if not isinstance(elements, list):
            return result
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("Road-route estimate unavailable: %s", type(exc).__name__)
        return result

    enriched = [station.copy() for station in stations]
    seen = set()
    for element in elements:
        if not isinstance(element, dict) or element.get("originIndex") != 0:
            continue
        destination_index = element.get("destinationIndex")
        if (
            not isinstance(destination_index, int)
            or isinstance(destination_index, bool)
            or not 0 <= destination_index < len(eligible)
            or destination_index in seen
            or element.get("condition") != "ROUTE_EXISTS"
            or not isinstance(element.get("status", {}), dict)
            or element.get("status", {}).get("code", 0) != 0
        ):
            continue
        seen.add(destination_index)
        meters = element.get("distanceMeters")
        seconds = element.get("duration")
        if (
            not isinstance(meters, (int, float))
            or isinstance(meters, bool)
            or not math.isfinite(meters)
            or meters < 0
            or not isinstance(seconds, str)
            or not seconds.endswith("s")
        ):
            continue
        try:
            duration_seconds = float(seconds[:-1])
        except ValueError:
            continue
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            continue

        station_index = eligible[destination_index][0]
        enriched[station_index]["road_distance_miles"] = round(
            meters / METERS_PER_MILE, 2
        )
        enriched[station_index]["road_eta_minutes"] = max(
            1, math.ceil(duration_seconds / 60)
        )

    # Do not mutate the original provider response; route failures never
    # modify ranking, estimated cost or place data.
    return {**result, "stations": enriched}
