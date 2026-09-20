"""Optional, capped Google Routes matrix enrichment for displayed stations.

Only the five displayed candidates are sent to Routes. Driving-based ranking
can reorder those candidates, but not the entire Places candidate pool.
No route/Places responses are persisted or cached.
"""

import logging
import math

import httpx

from app.config import GOOGLE_MAPS_API_KEY, ROUTES_MAX_DESTINATIONS
from app.utils.cost import calculate_estimated_cost

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
    fails, keep the original station data; callers must not describe
    geographical fallback distance as actual driving distance.
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
    except httpx.HTTPStatusError as exc:
        # Do not log the response body, request headers, key or coordinates.
        # Only the HTTP code and Google's machine-readable error category
        # are needed to distinguish API permissions from request errors.
        error_status = None
        try:
            error = exc.response.json().get("error", {})
            if isinstance(error, dict):
                status = error.get("status")
                if status in {
                    "PERMISSION_DENIED", "FAILED_PRECONDITION",
                    "INVALID_ARGUMENT", "RESOURCE_EXHAUSTED",
                    "UNAUTHENTICATED", "NOT_FOUND", "UNAVAILABLE",
                }:
                    error_status = status
        except (ValueError, TypeError, AttributeError):
            pass
        logger.warning(
            "Road-route request rejected: http_status=%s google_status=%s",
            exc.response.status_code,
            error_status or "unknown",
        )
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

    # Do not mutate the original provider response.
    return {**result, "stations": enriched}



def rank_displayed_stations_by_road(
    result: dict,
    *,
    sort: str,
    gallons_needed: float,
    vehicle_mpg: float,
) -> dict:
    """Use actual routes to rank the fetched/displayed candidates only.

    Preserve the provider's open-before-unknown-hours policy. A destination
    with no valid route must not be ranked as closest using geographic miles.
    Price sort is left unchanged. Recalculate estimated round-trip cost from
    driving miles when ranking 'best'; unknown-route candidates do not receive
    a fabricated road-based cost.
    """
    stations = result.get("stations", [])
    if sort == "price" or not any(
        station.get("road_distance_miles") is not None for station in stations
    ):
        return result

    updated = []
    for station in stations:
        item = station.copy()
        road_miles = item.get("road_distance_miles")
        if sort == "best":
            price = item.get("selected_fuel", {}).get("price")
            item["estimated_cost"] = (
                calculate_estimated_cost(
                    price_per_gallon=price,
                    distance_miles=road_miles,
                    gallons_needed=gallons_needed,
                    vehicle_mpg=vehicle_mpg,
                )
                if road_miles is not None and price is not None
                else None
            )
        updated.append(item)

    def sort_key(station: dict) -> tuple:
        road_miles = station.get("road_distance_miles")
        open_priority = 0 if station.get("open_now") is True else 1
        if sort == "best":
            cost = station.get("estimated_cost")
            return (
                open_priority,
                cost is None,
                cost["estimated_total_cost"] if cost else float("inf"),
                road_miles if road_miles is not None else float("inf"),
            )
        return (
            open_priority,
            road_miles is None,
            road_miles if road_miles is not None else float("inf"),
        )

    updated.sort(key=sort_key)
    return {**result, "stations": updated}
