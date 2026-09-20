import pytest

from app.conversation import ConversationSession, ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.models import IncomingMessage


SENDER = "15551234567"


def saved_location_session():
    whatsapp_handler.conversation_store.clear()
    return whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )


@pytest.mark.parametrize("selection_id", ["lang_en", "lang_es"])
def test_old_language_button_cannot_reset_pending_location(
    monkeypatch, selection_id
):
    expected_session = saved_location_session()
    sent = []
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent.append(kwargs),
    )

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            selection_id=selection_id,
        )
    )

    assert whatsapp_handler.conversation_store.get(SENDER) == expected_session
    assert len(sent) == 1
    assert "esperando tu ubicación" in sent[0]["message"].lower()


@pytest.mark.parametrize(
    "text",
    [
        "Busca diésel más barato",
        "ok",
        "something unrelated",
    ],
)
def test_text_while_waiting_for_location_does_not_change_preferences(
    monkeypatch, text
):
    expected_session = saved_location_session()
    sent = []

    def unexpected_interpretation(_text):
        raise AssertionError("No new search should start while awaiting location")

    monkeypatch.setattr(
        whatsapp_handler.intent_interpreter,
        "interpret",
        unexpected_interpretation,
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=SENDER,
            message_type="text",
            text=text,
        )
    )

    assert whatsapp_handler.conversation_store.get(SENDER) == expected_session
    assert len(sent) == 1
    assert "esperando tu ubicación" in sent[0]["message"].lower()


def test_language_button_works_at_language_selection(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_LANGUAGE
    )
    sent = []
    monkeypatch.setattr(
        whatsapp_handler,
        "send_list_message",
        lambda **kwargs: sent.append(kwargs),
    )

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            selection_id="lang_es",
        )
    )

    session = whatsapp_handler.conversation_store.get(SENDER)
    assert session.state == ConversationState.MAIN_MENU
    assert session.language == "es"
    assert [row["id"] for row in sent[0]["rows"]] == [
        "home_search", "fav_list", "account_plan", "nav_language",
    ]


def test_menu_still_resets_flow_while_waiting_for_location(monkeypatch):
    saved_location_session()
    sent = []
    monkeypatch.setattr(
        whatsapp_handler,
        "send_list_message",
        lambda **kwargs: sent.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=SENDER,
            message_type="text",
            text="menú",
        )
    )

    assert whatsapp_handler.conversation_store.get(SENDER) == (
        ConversationSession(
            sender=SENDER,
            state=ConversationState.MAIN_MENU,
            language="es",
            fuel_type="premium",
            sort="price",
            max_distance_miles=3,
        )
    )
    assert [row["id"] for row in sent[0]["rows"]] == [
        "home_search", "fav_list", "account_plan", "nav_language",
    ]
