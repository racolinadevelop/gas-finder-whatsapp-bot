import pytest

from app.conversation import ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.models import IncomingMessage
from app.providers import GasStationProviderError
from app.services.whatsapp import WhatsAppServiceError


def prepare_session(language="en"):
    sender = "15551234567"
    whatsapp_handler.conversation_store.clear()
    session = whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_LOCATION,
        language=language,
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )
    message = IncomingMessage(
        sender=sender,
        message_type="location",
        latitude=38.2527,
        longitude=-85.7585,
    )
    return sender, session, message


def test_session_is_preserved_after_result_and_navigation_is_offered(monkeypatch):
    sender, expected_session, message = prepare_session()
    events = []

    class SuccessfulSearch:
        def search(self, **kwargs):
            assert whatsapp_handler.conversation_store.get(sender) == (
                expected_session
            )
            events.append("searched")
            return "Search results"

    def successful_send(**kwargs):
        assert whatsapp_handler.conversation_store.get(sender) == (
            expected_session
        )
        events.append("sent")

    monkeypatch.setattr(
        whatsapp_handler,
        "location_search_service",
        SuccessfulSearch(),
    )
    def send_actions(**kwargs):
        assert whatsapp_handler.conversation_store.get(sender).state == (
            ConversationState.WAITING_RESULTS
        )
        assert [row["id"] for row in kwargs["rows"]] == [
            "nav_back",
            "nav_menu",
        ]
        events.append("actions")

    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        successful_send,
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_list_message",
        send_actions,
    )

    whatsapp_handler.handle_location_message(message)

    assert events == ["searched", "sent", "actions"]
    assert whatsapp_handler.conversation_store.get(sender).state == (
        ConversationState.WAITING_RESULTS
    )
    assert whatsapp_handler.conversation_store.get(sender).fuel_type == (
        expected_session.fuel_type
    )


@pytest.mark.parametrize(
    ("language", "expected_text"),
    [
        ("en", "preferences are still saved"),
        ("es", "preferencias siguen guardadas"),
    ],
)
def test_provider_error_preserves_session_and_sends_retry_prompt(
    monkeypatch,
    language,
    expected_text,
):
    sender, expected_session, message = prepare_session(language)
    sent_messages = []

    class FailingSearch:
        def search(self, **kwargs):
            raise GasStationProviderError("provider unavailable")

    monkeypatch.setattr(
        whatsapp_handler,
        "location_search_service",
        FailingSearch(),
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_location_message(message)

    assert whatsapp_handler.conversation_store.get(sender) == expected_session
    assert expected_text in sent_messages[0]["message"]


def test_whatsapp_send_error_preserves_session(monkeypatch):
    sender, expected_session, message = prepare_session()

    class SuccessfulSearch:
        def search(self, **kwargs):
            return "Search results"

    def failing_send(**kwargs):
        raise WhatsAppServiceError("WhatsApp unavailable")

    monkeypatch.setattr(
        whatsapp_handler,
        "location_search_service",
        SuccessfulSearch(),
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        failing_send,
    )

    whatsapp_handler.handle_location_message(message)

    assert whatsapp_handler.conversation_store.get(sender) == expected_session
