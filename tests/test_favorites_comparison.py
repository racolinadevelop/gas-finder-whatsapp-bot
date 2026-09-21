"""Saved station comparison refreshes only selected Google Places and never invents prices."""

from unittest.mock import Mock

import httpx
import pytest

from app.favorites.comparison import (
    DETAILS_FIELD_MASK,
    MAX_COMPARED_FAVORITES,
    compare_saved_places,
    fetch_saved_place_details,
    format_favorite_comparison,
)
from app.favorites.models import FavoriteStation


def favorite(index: int) -> FavoriteStation:
    return FavoriteStation(
        key=f"place:validPlace{index}",
        name=f"Station {index}",
        address=f"{index} Main Street",
    )


def details(index: int, *, regular: int | None, open_now=True) -> dict:
    prices = []
    if regular is not None:
        prices = [{
            "type": "REGULAR_UNLEADED",
            "price": {"units": regular, "nanos": 250_000_000, "currencyCode": "USD"},
            "updateTime": "2026-09-20T20:00:00Z",
        }]
    return {
        "id": f"validPlace{index}",
        "location": {"latitude": 38.1 + index * 0.01, "longitude": -85.7},
        "businessStatus": "OPERATIONAL",
        "currentOpeningHours": {"openNow": open_now},
        "fuelOptions": {"fuelPrices": prices},
    }


def test_details_uses_one_safe_api_get_with_minimum_fields(monkeypatch):
    requests = []
    def fake_get(url, **kwargs):
        requests.append((url, kwargs))
        return httpx.Response(200, json=details(1, regular=3),
                              request=httpx.Request("GET", url))
    monkeypatch.setattr("app.favorites.comparison.httpx.get", fake_get)
    result = fetch_saved_place_details("validPlace1", api_key="test-key")
    assert result["id"] == "validPlace1"
    assert len(requests) == 1
    url, opts = requests[0]
    assert url.endswith("/validPlace1")
    assert opts["headers"]["X-Goog-FieldMask"] == DETAILS_FIELD_MASK
    assert opts["headers"]["X-Goog-Api-Key"] == "test-key"
    assert "displayName" not in DETAILS_FIELD_MASK

    for invalid in ("", "../users", "places/other", "bad id"):
        assert fetch_saved_place_details(invalid, api_key="test-key") is None
    assert fetch_saved_place_details("validPlace1", api_key="") is None
    assert len(requests) == 1


def test_compare_price_sort_unknown_last_and_one_route_matrix_for_five():
    called, matrix = [], []
    def load(place_id):
        called.append(place_id)
        number = int(place_id[-1])
        return details(number, regular={1: 4, 2: 3, 3: None, 4: 5, 5: 2}[number])

    def route(result, **kwargs):
        matrix.append((result, kwargs))
        assert len(result["stations"]) == 5
        assert set(kwargs) == {"latitude", "longitude"}
        return {"stations": [
            {**station, "road_distance_miles": number + 1.0,
             "road_eta_minutes": number + 2}
            for number, station in enumerate(result["stations"])
        ]}

    selected = tuple(favorite(i) for i in range(1, 6))
    outcome = compare_saved_places(
        selected, latitude=38.25, longitude=-85.75,
        fuel_type="regular", fetch_details=load,
        routes_enabled=True, enrich_routes=route,
    )
    assert len(called) == 5 and len(matrix) == 1
    assert [s["name"] for s in outcome["stations"]] == [
        "Station 5", "Station 2", "Station 1", "Station 4", "Station 3",
    ]
    output = format_favorite_comparison(outcome, "es")
    assert "$2.250/gal" in output
    assert "Precio no disponible" in output
    assert "🚗 5.00 mi" in output
    assert "Precios reportados" in output
    assert "Station 6" not in output
    for station in outcome["stations"]:
        assert "latitude" in station  # ephemeral only, never stored


def test_compare_skips_closed_and_unknown_details_without_stale_saved_prices():
    called = []
    def load(place_id):
        called.append(place_id)
        return (
            details(1, regular=3, open_now=False)
            if place_id == "validPlace1" else None
        )
    result = compare_saved_places(
        (favorite(1), favorite(2)), latitude=38.2, longitude=-85.7,
        fuel_type="diesel", fetch_details=load, routes_enabled=False,
    )
    assert called == ["validPlace1", "validPlace2"]
    assert all(station["selected_fuel"]["price"] is None
               for station in result["stations"])
    message = format_favorite_comparison(result, "en")
    assert "Closed" in message
    assert "Price unavailable" in message
    assert "Driving route unavailable" in message
    assert "Station information is temporarily unavailable" in message
    assert "last saved price" not in message


def test_compare_invalid_or_unlocatable_ids_never_trigger_search_or_routes():
    calls = []
    missing = FavoriteStation(
        key="location:abc", name="Older Station", address="Main St",
    )
    result = compare_saved_places(
        (missing, favorite(2)), latitude=38.2, longitude=-85.7,
        fuel_type="regular",
        fetch_details=lambda pid: calls.append(pid) or {
            "id": pid, "fuelOptions": {},
        },
        routes_enabled=True,
        enrich_routes=lambda *_a, **_k: pytest.fail("No coordinates for routing"),
    )
    assert calls == ["validPlace2"]
    assert all(station["selected_fuel"]["price"] is None
               for station in result["stations"])
    with pytest.raises(ValueError):
        compare_saved_places(
            tuple(favorite(i) for i in range(6)),
            latitude=38.2, longitude=-85.7, fuel_type="regular",
        )
    with pytest.raises(ValueError):
        compare_saved_places(
            (favorite(1),), latitude=38.2, longitude=-85.7, fuel_type="wrong",
        )
