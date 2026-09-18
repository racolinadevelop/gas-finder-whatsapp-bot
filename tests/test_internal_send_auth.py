from fastapi.testclient import TestClient

from app.main import app
from app.routers import whatsapp as whatsapp_router
from app.security import internal_api


client = TestClient(app)


def test_send_message_is_disabled_without_internal_token(monkeypatch):
    monkeypatch.setattr(internal_api, "INTERNAL_API_TOKEN", None)

    response = client.post(
        "/api/v1/whatsapp/send-message",
        json={
            "to": "15551234567",
            "message": "test",
        },
    )

    assert response.status_code == 503


def test_send_message_rejects_missing_bearer_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        "test-internal-token",
    )

    response = client.post(
        "/api/v1/whatsapp/send-message",
        json={
            "to": "15551234567",
            "message": "test",
        },
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_send_message_rejects_wrong_bearer_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        "test-internal-token",
    )

    response = client.post(
        "/api/v1/whatsapp/send-message",
        headers={"Authorization": "Bearer wrong-token"},
        json={
            "to": "15551234567",
            "message": "test",
        },
    )

    assert response.status_code == 401


def test_send_message_accepts_valid_bearer_token(monkeypatch):
    monkeypatch.setattr(
        internal_api,
        "INTERNAL_API_TOKEN",
        "test-internal-token",
    )
    sent = []
    monkeypatch.setattr(
        whatsapp_router,
        "send_text_message",
        lambda **kwargs: sent.append(kwargs)
        or {"messages": [{"id": "wamid.internal"}]},
    )

    response = client.post(
        "/api/v1/whatsapp/send-message",
        headers={
            "Authorization": "Bearer test-internal-token",
        },
        json={
            "to": "15551234567",
            "message": "Internal test",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "messages": [{"id": "wamid.internal"}]
    }
    assert sent == [
        {
            "to": "15551234567",
            "message": "Internal test",
        }
    ]
