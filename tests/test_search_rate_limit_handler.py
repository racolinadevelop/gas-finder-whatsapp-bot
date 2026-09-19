from app.conversation import ConversationSession, ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.models import IncomingMessage


class DenySearchRateLimiter:
    def allow(self, user_id: str) -> bool:
        return False

    def clear(self) -> None:
        return None


def test_rate_limited_location_does_not_call_station_provider(monkeypatch):
    incoming_message = IncomingMessage(
        sender="15551234567",
        message_type="location",
        message_id="wamid.rate-limited",
        latitude=38.25,
        longitude=-85.75,
    )
    session = ConversationSession(
        sender="15551234567",
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="regular",
        sort="best",
    )
    sent = []

    monkeypatch.setattr(
        whatsapp_handler,
        "search_rate_limiter",
        DenySearchRateLimiter(),
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent.append(kwargs),
    )
    monkeypatch.setattr(
        whatsapp_handler.location_search_service,
        "search",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("provider search should not be called")
        ),
    )

    whatsapp_handler.search_from_location(
        incoming_message,
        session,
    )

    assert len(sent) == 1
    assert sent[0]["to"] == "15551234567"
    assert "demasiadas búsquedas" in sent[0]["message"].lower()
