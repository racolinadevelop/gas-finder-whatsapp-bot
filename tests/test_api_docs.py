from fastapi.testclient import TestClient

from app.main import create_app


def test_api_docs_can_be_disabled():
    client = TestClient(create_app(api_docs_enabled=False))

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_health_remains_available_when_docs_are_disabled():
    client = TestClient(create_app(api_docs_enabled=False))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_docs_can_be_enabled_for_local_development():
    client = TestClient(create_app(api_docs_enabled=True))

    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
