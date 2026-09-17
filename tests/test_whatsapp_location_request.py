from app.services import whatsapp as whatsapp_service


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"messages": [{"id": "wamid.test"}]}


def _configure_whatsapp(monkeypatch):
    monkeypatch.setattr(whatsapp_service, "WHATSAPP_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(whatsapp_service, "WHATSAPP_PHONE_NUMBER_ID", "123456")
    monkeypatch.setattr(whatsapp_service, "WHATSAPP_API_VERSION", "v25.0")


def test_spanish_location_prompt_uses_native_location_request(monkeypatch):
    _configure_whatsapp(monkeypatch)
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(whatsapp_service.httpx, "post", fake_post)

    whatsapp_service.send_text_message(
        to="15551234567",
        message=(
            "¡Perfecto! ✅ Tu búsqueda está lista.\n\n"
            "📍 Ahora comparte tu ubicación y buscaré las mejores opciones "
            "cercanas para ti."
        ),
    )

    payload = captured["payload"]
    assert payload["type"] == "interactive"
    assert payload["interactive"]["type"] == "location_request_message"
    assert payload["interactive"]["action"] == {"name": "send_location"}
    assert "comparte tu ubicación" in payload["interactive"]["body"]["text"]


def test_english_location_retry_uses_native_location_request(monkeypatch):
    _configure_whatsapp(monkeypatch)
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return FakeResponse()

    monkeypatch.setattr(whatsapp_service.httpx, "post", fake_post)

    whatsapp_service.send_text_message(
        to="15551234567",
        message="📍 I'm waiting for your location. Please share your location.",
    )

    assert captured["payload"]["interactive"]["type"] == (
        "location_request_message"
    )
    assert captured["payload"]["interactive"]["action"]["name"] == (
        "send_location"
    )


def test_regular_text_message_stays_text(monkeypatch):
    _configure_whatsapp(monkeypatch)
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return FakeResponse()

    monkeypatch.setattr(whatsapp_service.httpx, "post", fake_post)

    whatsapp_service.send_text_message(
        to="15551234567",
        message="Hello from Gas Finder",
    )

    assert captured["payload"]["type"] == "text"
    assert captured["payload"]["text"]["body"] == "Hello from Gas Finder"
