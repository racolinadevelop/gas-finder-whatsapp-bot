import httpx

from app.providers import GasStationProviderError
from app.services.google_places import deduplicate_stations, sort_stations
from app.utils.cost import calculate_estimated_cost
from app.utils.distance import calculate_distance_miles

HERE_FUEL_STATIONS_URL = "https://fuel.hereapi.com/v3/stations"
HERE_CANDIDATE_LIMIT = 50
METERS_PER_MILE = 1609.344
HERE_FUEL_TYPE_MAP = {
    "regular": 2,
    "premium": 4,
    "diesel": 1,
}


class HereFuelPricesProvider:
    """HERE Fuel Prices API adapter using the app's existing result shape."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_nearby(
        self,
        *,
        latitude: float,
        longitude: float,
        radius: float = 5000,
        fuel_type: str = "regular",
        sort: str = "distance",
        limit: int = 10,
        gallons_needed: float = 10,
        vehicle_mpg: float = 25,
    ) -> dict:
        here_fuel_type = HERE_FUEL_TYPE_MAP[fuel_type]
        params = {
            "in": f"circle:{latitude},{longitude};r={int(radius)}",
            "fuelTypes": str(here_fuel_type),
            "limit": HERE_CANDIDATE_LIMIT,
            "sort": "price:asc" if sort == "price" else "distance:asc",
            "returnAllStations": "false",
            "apiKey": self.api_key,
        }

        try:
            response = httpx.get(
                HERE_FUEL_STATIONS_URL,
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise GasStationProviderError(
                "HERE Fuel Prices took too long to respond.", 504
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 429:
                raise GasStationProviderError(
                    "HERE Fuel Prices request limit has been reached.", 503
                ) from exc
            if status_code in (401, 403):
                raise GasStationProviderError(
                    "HERE Fuel Prices authentication or permission error.", 502
                ) from exc
            if status_code >= 500:
                raise GasStationProviderError(
                    "HERE Fuel Prices is temporarily unavailable.", 503
                ) from exc
            raise GasStationProviderError(
                "HERE Fuel Prices request failed.", 502
            ) from exc
        except httpx.RequestError as exc:
            raise GasStationProviderError(
                "Unable to connect to HERE Fuel Prices.", 502
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise GasStationProviderError(
                "HERE Fuel Prices returned an invalid response.", 502
            ) from exc

        stations = []
        for item in data.get("stations", []):
            station = self._parse_station(
                item=item,
                origin_latitude=latitude,
                origin_longitude=longitude,
                fuel_type=fuel_type,
                here_fuel_type=here_fuel_type,
                gallons_needed=gallons_needed,
                vehicle_mpg=vehicle_mpg,
            )
            if station is not None:
                stations.append(station)

        stations = deduplicate_stations(stations)
        stations = sort_stations(stations, sort)[:limit]

        return {
            "stations": stations,
            "count": len(stations),
            "message": (
                "Gas stations found."
                if stations
                else "No gas stations with an available price were found."
            ),
        }

    def _parse_station(
        self,
        *,
        item: dict,
        origin_latitude: float,
        origin_longitude: float,
        fuel_type: str,
        here_fuel_type: int,
        gallons_needed: float,
        vehicle_mpg: float,
    ) -> dict | None:
        position = item.get("position", {})
        latitude = position.get("lat")
        longitude = position.get("lng")
        if latitude is None or longitude is None:
            return None

        matching_price = next(
            (
                price
                for price in item.get("prices", [])
                if str(price.get("fuelType")) == str(here_fuel_type)
                and price.get("available", True)
                and price.get("price") is not None
            ),
            None,
        )
        if matching_price is None:
            return None

        distance_meters = item.get("distance")
        distance_miles = (
            distance_meters / METERS_PER_MILE
            if distance_meters is not None
            else calculate_distance_miles(
                origin_latitude,
                origin_longitude,
                latitude,
                longitude,
            )
        )
        selected_fuel = {
            "available": True,
            "price": round(float(matching_price["price"]), 3),
            "currency": matching_price.get("currency", "USD"),
            "updated_at": matching_price.get("modified"),
        }
        estimated_cost = calculate_estimated_cost(
            price_per_gallon=selected_fuel["price"],
            distance_miles=distance_miles,
            gallons_needed=gallons_needed,
            vehicle_mpg=vehicle_mpg,
        )

        return {
            "id": item.get("id"),
            "name": item.get("name") or item.get("brand") or "Unknown gas station",
            "address": item.get("address", {}).get(
                "label", "Address not available"
            ),
            "latitude": latitude,
            "longitude": longitude,
            "distance_miles": distance_miles,
            "fuel_prices": {fuel_type: selected_fuel.copy()},
            "selected_fuel": selected_fuel,
            "estimated_cost": estimated_cost,
        }
