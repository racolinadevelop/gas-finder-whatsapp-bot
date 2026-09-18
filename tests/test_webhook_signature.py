import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import app
from app.routers import whatsapp as whatsapp_router
from app.security import verify_meta_webhook_signature


client = TestClient(app)


def _signature(secret: str, raw_body: bytes) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def test_meta_signature_validation_accepts_valid_signature():
    raw_body = b'{"object":"whatsapp_business_account"}'
    secret = "test-app-secret"

    assert verify_meta_webhook_signature(
        raw_body,
        _signature(secret, raw_body),
        secret,
    ) is True


def test_meta_signature_validation_rejects_invalid_signature():
    assert verify_meta_webhook_signature(
        b'{"event":"test"}',
        "sha256=invalid",
        "test-app-secret",
    ) is False


def test_webhook_rejects_invalid_signature_when_secret_is_configured(
    monkeypatch,
):
    monkeypatch.setattr(
        whatsapp_router,
        "META_APP_SECRET",
        "test-app-secret",
    )
    dispatched = []
    monkeypatch.setattr(
        whatsapp_router,
        "handle_whatsapp_webhook",
        lambda payload: dispatched.append(payload) or {"status": "ok"},
    )

    response = client.post(
        "/api/v1/whatsapp/webhook",
        content=b'{"event":"forged"}',
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": "sha256=invalid",
        },
    )

    assert response.status_code == 401
    assert dispatched == []


def test_webhook_accepts_valid_signature_when_secret_is_configured(
    monkeypatch,
):
    secret = "test-app-secret"
    payload = {"event": "real"}
    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    monkeypatch.setattr(
        whatsapp_router,
        "META_APP_SECRET",
        secret,
    )
    dispatched = []
    monkeypatch.setattr(
        whatsapp_router,
        "handle_whatsapp_webhook",
        lambda value: dispatched.append(value) or {"status": "ok"},
    )

    response = client.post(
        "/api/v1/whatsapp/webhook",
        content=raw_body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": _signature(secret, raw_body),
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert dispatched == [payload]
