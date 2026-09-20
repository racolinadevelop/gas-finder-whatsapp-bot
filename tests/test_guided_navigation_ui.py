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
        (ConversationState.WAITING_FUEL, "list"),
        (ConversationState.WAITING_SORT, "list"),
        (ConversationState.WAITING_DISTANCE, "list"),
        (ConversationState.WAITING_CUSTOM_DISTANCE, "text"),
    ],
)
def test_second_screen_onwards_has_combined_navigation_list(
    monkeypatch, state, primary_kind
):
    whatsapp_handler.conversation_store.clear()
    session = whatsapp_handler.conversation_store.update(
        SENDER, state=state, language="es", fuel_type="premium",
        sort="price", max_distance_miles=3,
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.send_state_prompt(SENDER, session)

    assert [kind for kind, _ in sent] == (
        ["text", "list"] if primary_kind == "text" else ["list"]
    )
    navigation = sent[-1][1]["rows"][-2:]
    assert [row["id"] for row in navigation] == ["nav_back", "nav_menu"]
    assert [row["title"] for row in navigation] == ["⬅️ Atrás", "🏠 Menú"]

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
    "account_plan",
    ]
    assert sent[0][1]["body_text"].count("Ramon") == 2


def test_language_selection_does_not_greet_again_and_has_navigation(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_LANGUAGE,
        profile_name="Ramon",
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(sender=SENDER, message_type="interactive",
                        selection_id="lang_es", profile_name="Ramon")
    )

    assert len(sent) == 1
    assert sent[0][0] == "list"
    assert [row["id"] for row in sent[0][1]["rows"]] == [
        "fuel_regular", "fuel_premium", "fuel_diesel", "nav_back", "nav_menu",
    ]
    assert sent[0][1]["button_text"] == "Elegir combustible"
    assert "Hola, Ramon" not in sent[0][1]["body_text"]
    assert "bienvenido" not in sent[0][1]["body_text"].lower()

def test_results_screen_keeps_its_own_navigation_without_duplicates(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    session = whatsapp_handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_RESULTS, language="es",
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.send_state_prompt(SENDER, session)

    assert [kind for kind, _ in sent] == ["list"]
    assert [row["id"] for row in sent[0][1]["rows"]] == [
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
    "account_plan",
    ]
    assert "Welcome" not in sent[0][1]["body_text"]
    assert "Ramon" not in sent[0][1]["body_text"]


def test_location_step_sends_navigation_below_native_location_request(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    session = whatsapp_handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_LOCATION,
        language="es", fuel_type="premium", sort="price", max_distance_miles=3,
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.send_state_prompt(SENDER, session)

    assert [kind for kind, _ in sent] == ["text", "list"]
    assert [row["id"] for row in sent[1][1]["rows"]] == [
        "nav_back", "nav_menu",
    ]
    assert [row["title"] for row in sent[1][1]["rows"]] == [
        "⬅️ Atrás", "🏠 Menú",
    ]
    assert "esperando tu ubicación" in sent[0][1]["message"].lower()

def test_back_from_location_returns_to_distance_with_saved_preferences(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER, state=ConversationState.WAITING_LOCATION, language="es",
        fuel_type="premium", sort="price", max_distance_miles=3,
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(sender=SENDER, message_type="interactive",
                        interactive_type="list_reply", selection_id="nav_back")
    )

    session = whatsapp_handler.conversation_store.get(SENDER)
    assert session.state == ConversationState.WAITING_DISTANCE
    assert session.language == "es"
    assert session.fuel_type == "premium"
    assert session.sort == "price"
    assert session.max_distance_miles == 3
    assert [kind for kind, _ in sent] == ["list"]
    assert [row["id"] for row in sent[0][1]["rows"]] == [
        "distance_1", "distance_3", "distance_5", "distance_10",
        "distance_custom", "nav_back", "nav_menu",
    ]

def test_menu_from_location_restarts_without_repeating_greeting(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_LOCATION,
        profile_name="Ramon",
        language="es",
        fuel_type="premium",
        sort="price",
        max_distance_miles=3,
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            interactive_type="button_reply",
            selection_id="nav_menu",
        )
    )

    session = whatsapp_handler.conversation_store.get(SENDER)
    assert session.state == ConversationState.WAITING_LANGUAGE
    assert session.profile_name == "Ramon"
    assert [kind for kind, _ in sent] == ["buttons"]
    assert [button["id"] for button in sent[0][1]["buttons"]] == [
        "lang_en", "lang_es",
    "account_plan",
    ]
    assert "Welcome" not in sent[0][1]["body_text"]
