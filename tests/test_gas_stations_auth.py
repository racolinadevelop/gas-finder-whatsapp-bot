from fastapi.testclient import TestClient

from app.main import app
from app.routers import gas_stations as gas_stations_router
from app.security import internal_api


client = TestClient(app)


def test_nearby_rejects_missing_internal_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        "test-internal-token",
    )
    called = []
    monkeypatch.setattr(
        gas_stations_router,
        "search_nearby_gas_stations",
        lambda **kwargs: called.append(kwargs) or {
            "stations": [],
            "count": 0,
        },
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        params={
            "latitude": 38.25,
            "longitude": -85.75,
        },
    )

    assert response.status_code == 401
    assert called == []


def test_nearby_rejects_wrong_internal_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        "test-internal-token",
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        headers={"Authorization": "Bearer wrong-token"},
        params={
            "latitude": 38.25,
            "longitude": -85.75,
        },
    )

    assert response.status_code == 401


def test_nearby_accepts_valid_internal_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        "test-internal-token",
    )
    monkeypatch.setattr(
        gas_stations_router,
        "search_nearby_gas_stations",
        lambda **kwargs: {
            "stations": [],
            "count": 0,
            "message": "No gas stations found in the selected area.",
        },
    )

    response = client.get(
        "/api/v1/gas-stations/nearby",
        headers={
            "Authorization": "Bearer test-internal-token",
        },
        params={
            "latitude": 38.25,
            "longitude": -85.75,
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0
