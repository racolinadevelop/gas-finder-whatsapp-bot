import pytest

from app.conversation import ConversationState
from app.handlers import whatsapp as whatsapp_handler
from app.models import IncomingMessage


SENDER = "15551234567"


def capture_sent_prompts(monkeypatch):
    sent = []
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent.append(("buttons", kwargs)),
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_list_message",
        lambda **kwargs: sent.append(("list", kwargs)),
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent.append(("text", kwargs)),
    )
    return sent


@pytest.mark.parametrize(
    ("state", "primary_kind"),
    [
        (ConversationState.WAITING_FUEL, "buttons"),
        (ConversationState.WAITING_SORT, "buttons"),
        (ConversationState.WAITING_DISTANCE, "list"),
        (ConversationState.WAITING_CUSTOM_DISTANCE, "text"),
        (ConversationState.WAITING_LOCATION, "text"),
    ],
)
def test_second_screen_onwards_has_back_and_menu_buttons(
    monkeypatch, state, primary_kind
):
    whatsapp_handler.conversation_store.clear()
    session = whatsapp_handler.conversation_store.update(
        SENDER,
        state=state,
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.send_state_prompt(SENDER, session)

    assert len(sent) == 2
    assert sent[0][0] == primary_kind
    assert sent[1][0] == "buttons"
    assert [button["id"] for button in sent[1][1]["buttons"]] == [
        "nav_back", "nav_menu",
    ]
    assert [button["title"] for button in sent[1][1]["buttons"]] == [
        "⬅️ Atrás", "🏠 Menú",
    ]


def test_first_language_screen_only_has_language_buttons(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=SENDER,
            message_type="text",
            text="hola",
            profile_name="Ramon",
        )
    )

    assert len(sent) == 1
    assert [button["id"] for button in sent[0][1]["buttons"]] == [
        "lang_en", "lang_es",
    ]
    assert sent[0][1]["body_text"].count("Ramon") == 2


def test_language_selection_does_not_greet_again_and_has_navigation(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_LANGUAGE,
        profile_name="Ramon",
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            selection_id="lang_es",
            profile_name="Ramon",
        )
    )

    assert len(sent) == 2
    assert [button["id"] for button in sent[0][1]["buttons"]] == [
        "fuel_regular", "fuel_premium", "fuel_diesel",
    ]
    assert "Hola, Ramon" not in sent[0][1]["body_text"]
    assert "bienvenido" not in sent[0][1]["body_text"].lower()
    assert [button["id"] for button in sent[1][1]["buttons"]] == [
        "nav_back", "nav_menu",
    ]


def test_results_screen_keeps_its_own_navigation_without_duplicates(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    session = whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_RESULTS,
        language="es",
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.send_state_prompt(SENDER, session)

    assert len(sent) == 1
    assert [button["id"] for button in sent[0][1]["buttons"]] == [
        "nav_back", "nav_menu",
    ]


def test_back_button_from_second_screen_returns_to_language_without_greeting(
    monkeypatch,
):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_FUEL,
        language="es",
        profile_name="Ramon",
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            selection_id="nav_back",
        )
    )

    assert whatsapp_handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )
    assert len(sent) == 1
    assert [button["id"] for button in sent[0][1]["buttons"]] == [
        "lang_en", "lang_es",
    ]
    assert "Welcome" not in sent[0][1]["body_text"]
    assert "Ramon" not in sent[0][1]["body_text"]
