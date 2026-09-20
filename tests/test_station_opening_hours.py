"""Opening-hours regression coverage without external Google API calls."""

import pytest

from app.services.google_places import (
    parse_open_now,
    search_nearby_gas_stations,
    sort_stations,
)
from app.services.whatsapp import build_gas_stations_reply
from app.providers.here import HereFuelPricesProvider


def place(name, address, price, hours=None, business_status=None):
    item = {
        "id": name,
        "displayName": {"text": name},
        "formattedAddress": address,
        "location": {"latitude": 38.25, "longitude": -85.75},
        "fuelOptions": {
            "fuelPrices": [
                {
                    "type": "REGULAR_UNLEADED",
                    "price": {
                        "units": int(price),
                        "nanos": round((price - int(price)) * 1_000_000_000),
                        "currencyCode": "USD",
                    },
                }
            ]
        },
    }
    if hours is not None:
        item["currentOpeningHours"] = hours
    if business_status is not None:
        item["businessStatus"] = business_status
    return item


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (None, None),
        ({}, None),
        ({"openNow": None}, None),
        ({"openNow": "false"}, None),
        ({"openNow": False}, False),
        ({"openNow": True}, True),
    ],
)
def test_only_explicit_google_boolean_establishes_open_status(hours, expected):
    assert parse_open_now({"currentOpeningHours": hours}) is expected


def test_google_filters_closed_stations_but_keeps_unknown_as_fallback(
    monkeypatch,
):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    place("Sam's Club Gas Station", "6622 Preston Hwy", 2.49,
                          {"openNow": False}),
                    place("BP Open", "1 Main St", 3.99, {"openNow": True}),
                    place("Unknown Hours", "2 Main St", 2.89),
                    place("Not Operating", "3 Main St", 2.40,
                          business_status="CLOSED_PERMANENTLY"),
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured.update({"headers": headers, "payload": json})
        return FakeResponse()

    monkeypatch.setattr("app.services.google_places.httpx.post", fake_post)
    result = search_nearby_gas_stations(
        latitude=38.25, longitude=-85.75, fuel_type="regular",
        sort="price", radius=1609.344, limit=5,
    )

    assert "places.currentOpeningHours" in captured["headers"]["X-Goog-FieldMask"]
    assert "places.businessStatus" in captured["headers"]["X-Goog-FieldMask"]
    assert "openNow" not in captured["payload"]
    assert result["count"] == 2
    assert [station["name"] for station in result["stations"]] == [
        "BP Open", "Unknown Hours",
    ]
    assert [station["open_now"] for station in result["stations"]] == [
        True, None,
    ]
    reply = build_gas_stations_reply(result, language="es", sort="price")
    assert "Sam's Club" not in reply
    assert "Not Operating" not in reply
    assert "Abierta ahora" not in reply
    assert "Horario no disponible" not in reply
    assert "BP Open" in reply
    assert "Unknown Hours" in reply


def test_all_google_stations_explicitly_closed_yields_no_results(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"places": [
                place("Closed Station", "1 Main St", 2.49, {"openNow": False}),
            ]}

    monkeypatch.setattr(
        "app.services.google_places.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    result = search_nearby_gas_stations(
        latitude=38.25, longitude=-85.75,
        fuel_type="regular", sort="distance",
    )
    assert result["stations"] == []
    assert result["count"] == 0


@pytest.mark.parametrize("sort", ["price", "best", "distance"])
def test_known_open_stations_take_priority_over_unknown_hours(sort):
    known_open = {
        "name": "Open",
        "open_now": True,
        "distance_miles": 5.0,
        "selected_fuel": {"available": True, "price": 4.10},
        "estimated_cost": {"estimated_total_cost": 60},
    }
    unknown = {
        "name": "Unknown",
        "open_now": None,
        "distance_miles": 0.2,
        "selected_fuel": {"available": True, "price": 2.50},
        "estimated_cost": {"estimated_total_cost": 30},
    }
    assert sort_stations([unknown, known_open], sort)[0]["name"] == "Open"


def test_unverified_hours_never_display_as_open_in_whatsapp():
    reply = build_gas_stations_reply(
        {"stations": [{
            "name": "No schedule",
            "distance_miles": 1,
            "selected_fuel": {"available": True, "price": 3.10},
            "open_now": None,
        }]},
        language="en",
        sort="distance",
    )
    assert "No schedule" in reply
    assert "Opening hours unavailable" not in reply
    assert "Open now" not in reply


def test_here_fuel_price_does_not_imply_station_is_open(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"stations": [{
                "id": "here-1",
                "name": "Here Station",
                "address": {"label": "1 Main St"},
                "position": {"lat": 38.25, "lng": -85.75},
                "distance": 100,
                "prices": [{"fuelType": "2", "price": 3.05, "available": True}],
            }]}

    monkeypatch.setattr(
        "app.providers.here.httpx.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    result = HereFuelPricesProvider(api_key="dummy").search_nearby(
        latitude=38.25, longitude=-85.75,
        fuel_type="regular",
    )
    assert result["stations"][0]["open_now"] is None
    reply = build_gas_stations_reply(result, language="es")
    assert "Here Station" in reply
    assert "Horario no disponible" not in reply
    assert "Abierta ahora" not in reply


@pytest.mark.parametrize("language", ["es", "en"])
def test_whatsapp_excludes_confirmed_closed_station_and_counts_visible_only(language):
    def station(name, hours):
        return {
            "name": name,
            "open_now": hours,
            "distance_miles": 1.0,
            "selected_fuel": {"available": True, "price": 3.00},
        }

    reply = build_gas_stations_reply(
        {"stations": [station("Closed", False), station("Unknown", None),
                      station("Open", True)], "count": 3},
        language=language,
        sort="distance",
    )
    assert "1️⃣ Unknown" in reply
    assert "2️⃣ Open" in reply
    assert "Closed" not in reply
    assert ("Resultados mostrados: 2" if language == "es"
            else "Results shown: 2") in reply
    assert "Horario no disponible" not in reply
    assert "Opening hours unavailable" not in reply


@pytest.mark.parametrize("language", ["es", "en"])
def test_whatsapp_all_confirmed_closed_returns_no_results(language):
    reply = build_gas_stations_reply(
        {"stations": [{"name": "Closed", "open_now": False}]},
        language=language,
        sort="distance",
    )
    assert "Closed" not in reply
    assert ("No encontré gasolineras" if language == "es"
            else "I couldn't find nearby gas stations") in reply
