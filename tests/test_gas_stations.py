from fastapi.testclient import TestClient

from app.main import app
from app.services.google_places import (
    GooglePlacesServiceError,
    sort_stations,
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
