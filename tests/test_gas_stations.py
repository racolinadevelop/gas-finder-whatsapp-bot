from fastapi.testclient import TestClient

from app.main import app
from app.services.google_places import GooglePlacesServiceError

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
