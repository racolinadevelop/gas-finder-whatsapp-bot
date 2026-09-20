import pytest

from app.conversation import ConversationSession, ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.models import IncomingMessage
from app.services.whatsapp import WhatsAppServiceError


SENDER = "15551234567"


def completed_search():
    whatsapp_handler.conversation_store.clear()
    return whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_RESULTS,
        profile_name="Ramon",
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )


@pytest.mark.parametrize(
    "message_type,kwargs",
    [
        ("interactive", {"selection_id": "nav_back"}),
        ("text", {"text": "atrás"}),
    ],
)
def test_back_after_results_requests_new_location_with_same_preferences(
    monkeypatch, message_type, kwargs
):
    original = completed_search()
    sent = []
    monkeypatch.setattr(
        whatsapp_handler, "send_text_message",
        lambda **payload: sent.append(payload),
    )
    message = IncomingMessage(sender=SENDER, message_type=message_type, **kwargs)

    if message_type == "interactive":
        whatsapp_handler.handle_interactive_message(message)
    else:
        whatsapp_handler.handle_text_message(message)

    updated = whatsapp_handler.conversation_store.get(SENDER)
    assert updated == ConversationSession(
        sender=SENDER,
        state=ConversationState.WAITING_LOCATION,
        profile_name=original.profile_name,
        language=original.language,
        fuel_type=original.fuel_type,
        sort=original.sort,
        max_distance_miles=original.max_distance_miles,
    )
    assert len(sent) == 1
    assert "esperando tu ubicación" in sent[0]["message"].lower()


def test_menu_button_after_results_starts_over_without_repeating_greeting(
    monkeypatch,
):
    completed_search()
    sent = []
    monkeypatch.setattr(
        whatsapp_handler, "send_reply_buttons",
        lambda **payload: sent.append(payload),
    )

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            selection_id="nav_menu",
        )
    )

    assert whatsapp_handler.conversation_store.get(SENDER) == (
        ConversationSession(
            sender=SENDER,
            state=ConversationState.WAITING_LANGUAGE,
            profile_name="Ramon",
        )
    )
    assert "Ramon" not in sent[0]["body_text"]
    assert "choose your preferred language" in sent[0]["body_text"]
    assert [button["id"] for button in sent[0]["buttons"]] == [
        "lang_en", "lang_es",
    ]


@pytest.mark.parametrize(
    "message_type,kwargs",
    [
        ("interactive", {"selection_id": "fuel_diesel"}),
        ("text", {"text": "ok"}),
    ],
)
def test_unexpected_result_message_shows_navigation_buttons(
    monkeypatch, message_type, kwargs
):
    original = completed_search()
    sent = []
    monkeypatch.setattr(
        whatsapp_handler, "send_reply_buttons",
        lambda **payload: sent.append(payload),
    )
    message = IncomingMessage(sender=SENDER, message_type=message_type, **kwargs)

    if message_type == "interactive":
        whatsapp_handler.handle_interactive_message(message)
    else:
        whatsapp_handler.handle_text_message(message)

    assert whatsapp_handler.conversation_store.get(SENDER) == original
    assert [button["id"] for button in sent[0]["buttons"]] == [
        "nav_back", "nav_menu",
    ]


def test_failure_to_send_result_buttons_keeps_navigation_state(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )

    class SearchService:
        def search(self, **kwargs):
            return "Resultados"

    monkeypatch.setattr(
        whatsapp_handler, "location_search_service", SearchService()
    )
    monkeypatch.setattr(
        whatsapp_handler, "send_text_message", lambda **kwargs: None
    )

    def failed_buttons(**kwargs):
        raise WhatsAppServiceError("temporary error")

    monkeypatch.setattr(
        whatsapp_handler, "send_reply_buttons", failed_buttons
    )
    whatsapp_handler.handle_location_message(
        IncomingMessage(
            sender=SENDER,
            message_type="location",
            latitude=38.25,
            longitude=-85.75,
        )
    )

    assert whatsapp_handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_RESULTS
    )


def test_name_from_initial_greeting_is_retained_for_menu(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    sent = []
    monkeypatch.setattr(
        whatsapp_handler, "send_reply_buttons",
        lambda **payload: sent.append(payload),
    )
    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=SENDER,
            message_type="text",
            text="hola",
            profile_name="Ramon",
        )
    )
    assert whatsapp_handler.conversation_store.get(SENDER).profile_name == (
        "Ramon"
    )
    whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_RESULTS,
    )
    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=SENDER,
            message_type="text",
            text="menú",
        )
    )
    assert "Ramon" in sent[0]["body_text"]
    assert "Ramon" not in sent[-1]["body_text"]
    assert "choose your preferred language" in sent[-1]["body_text"]
    assert whatsapp_handler.conversation_store.get(SENDER).profile_name == "Ramon"
