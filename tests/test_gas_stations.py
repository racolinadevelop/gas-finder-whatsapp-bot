from fastapi.testclient import TestClient
from app.main import app
from app.services.google_places import (
    GooglePlacesServiceError,
    sort_stations,
)
from app.utils.cost import calculate_estimated_cost
from app.services.whatsapp import (
    build_text_reply,
    build_gas_stations_reply,
    parse_search_preferences,
)

client = TestClient(app)


def test_invalid_latitude():
    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 200,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 422


def test_google_timeout(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places took too long to respond.",
            status_code=504,
        )

    monkeypatch.setattr(
        "app.main.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 504

    assert response.json() == {"detail": "Google Places took too long to respond."}


def test_no_gas_stations(monkeypatch):
    def fake_search(*args, **kwargs):
        return {
            "stations": [],
            "count": 0,
            "message": "No gas stations found in the selected area.",
        }

    monkeypatch.setattr(
        "app.main.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["stations"] == []


def test_google_authentication_error(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places authentication or permission error.",
            status_code=502,
        )

    monkeypatch.setattr(
        "app.main.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Google Places authentication or permission error."
    }


def test_google_rate_limit(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places request limit has been reached.",
            status_code=503,
        )

    monkeypatch.setattr(
        "app.main.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Google Places request limit has been reached."
    }


def test_google_server_error(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Google Places is temporarily unavailable.",
            status_code=503,
        )

    monkeypatch.setattr(
        "app.main.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Google Places is temporarily unavailable."}


def test_google_connection_error(monkeypatch):
    def fake_search(*args, **kwargs):
        raise GooglePlacesServiceError(
            "Unable to connect to Google Places.",
            status_code=502,
        )

    monkeypatch.setattr(
        "app.main.search_nearby_gas_stations",
        fake_search,
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Unable to connect to Google Places."}


def test_sort_stations_by_price():
    stations = [
        {
            "name": "Shell",
            "distance_miles": 0.5,
            "selected_fuel": {
                "available": True,
                "price": 3.19,
            },
        },
        {
            "name": "Speedway",
            "distance_miles": 1.5,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
        {
            "name": "BP",
            "distance_miles": 0.2,
            "selected_fuel": {
                "available": False,
                "price": None,
            },
        },
    ]

    result = sort_stations(stations, "price")

    assert result[0]["name"] == "Speedway"
    assert result[1]["name"] == "Shell"
    assert result[2]["name"] == "BP"


def test_sort_stations_by_distance():
    stations = [
        {
            "name": "Shell",
            "distance_miles": 1.2,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
        {
            "name": "Speedway",
            "distance_miles": 0.4,
            "selected_fuel": {
                "available": True,
                "price": 3.09,
            },
        },
        {
            "name": "BP",
            "distance_miles": 2.1,
            "selected_fuel": {
                "available": False,
                "price": None,
            },
        },
    ]

    result = sort_stations(stations, "distance")

    assert result[0]["name"] == "Speedway"
    assert result[1]["name"] == "Shell"
    assert result[2]["name"] == "BP"


def test_sort_same_price_uses_distance():
    stations = [
        {
            "name": "Shell",
            "distance_miles": 1.8,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
        {
            "name": "Speedway",
            "distance_miles": 0.6,
            "selected_fuel": {
                "available": True,
                "price": 2.99,
            },
        },
    ]

    result = sort_stations(stations, "price")

    assert result[0]["name"] == "Speedway"
    assert result[1]["name"] == "Shell"


def test_invalid_limit():
    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.2527,
            "longitude": -85.7585,
            "radius": 5000,
            "fuel_type": "regular",
            "sort": "distance",
            "limit": 21,
        },
    )

    assert response.status_code == 422


def test_best_option_can_choose_closer_station():
    stations = [
        {
            "name": "Cheap but far",
            "distance_miles": 8.0,
            "selected_fuel": {
                "available": True,
                "price": 2.90,
            },
        },
        {
            "name": "Closer station",
            "distance_miles": 1.0,
            "selected_fuel": {
                "available": True,
                "price": 2.95,
            },
        },
    ]

    for station in stations:
        station["estimated_cost"] = calculate_estimated_cost(
            price_per_gallon=station["selected_fuel"]["price"],
            distance_miles=station["distance_miles"],
            gallons_needed=10,
            vehicle_mpg=25,
        )

    result = sort_stations(stations, "best")

    assert result[0]["name"] == "Closer station"


def test_build_text_reply_for_text_message():
    incoming_message = {
        "from": "15551234567",
        "type": "text",
        "message_id": "wamid.test",
        "text": "hello",
    }

    reply = build_text_reply(incoming_message)

    assert reply == (
        "Hi! 👋\n" "Send me your location and I'll find nearby gas stations for you."
    )


def test_build_text_reply_ignores_non_text_message():
    incoming_message = {
        "from": "15551234567",
        "type": "location",
        "message_id": "wamid.test",
        "latitude": 38.25,
        "longitude": -85.75,
    }

    reply = build_text_reply(incoming_message)

    assert reply is None


def test_build_gas_stations_reply_with_results():
    result = {
        "stations": [
            {
                "name": "Speedway",
                "distance_miles": 0.72,
                "selected_fuel": {
                    "available": True,
                    "price": 2.899,
                },
            },
            {
                "name": "Shell",
                "distance_miles": 1.14,
                "selected_fuel": {
                    "available": True,
                    "price": 2.999,
                },
            },
        ]
    }

    reply = build_gas_stations_reply(result)

    assert "Speedway" in reply
    assert "Shell" in reply
    assert "$2.899/gal" in reply
    assert "$2.999/gal" in reply
    assert "0.72 mi" in reply
    assert "1.14 mi" in reply


def test_build_gas_stations_reply_without_results():
    result = {"stations": []}

    reply = build_gas_stations_reply(result)

    assert "couldn't find gas stations" in reply


def test_parse_search_preferences_diesel_cheapest():
    result = parse_search_preferences("diesel cheapest")

    assert result == {
        "fuel_type": "diesel",
        "sort": "price",
    }


def test_parse_search_preferences_premium_closest():
    result = parse_search_preferences("premium closest")

    assert result == {
        "fuel_type": "premium",
        "sort": "distance",
    }


def test_parse_search_preferences_regular_best():
    result = parse_search_preferences("regular best")

    assert result == {
        "fuel_type": "regular",
        "sort": "best",
    }


def test_parse_search_preferences_case_insensitive():
    result = parse_search_preferences("DIESEL CHEAPEST")

    assert result == {
        "fuel_type": "diesel",
        "sort": "price",
    }


def test_parse_search_preferences_empty_text():
    result = parse_search_preferences("")

    assert result == {}
