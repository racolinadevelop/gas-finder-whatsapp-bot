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
    ("state", "expected_kind", "expected_rows"),
    [
        (ConversationState.WAITING_FUEL, "list",
         ["fuel_regular", "fuel_premium", "fuel_diesel", "nav_back", "nav_menu"]),
        (ConversationState.WAITING_SORT, "list",
         ["sort_distance", "sort_price", "sort_best", "nav_back", "nav_menu"]),
        (ConversationState.WAITING_DISTANCE, "list",
         ["distance_1", "distance_3", "distance_5", "distance_10",
          "distance_custom", "nav_back", "nav_menu"]),
        (ConversationState.WAITING_CUSTOM_DISTANCE, "text", None),
        (ConversationState.WAITING_LOCATION, "text", None),
    ],
)
def test_guided_step_is_single_message_with_navigation_only_in_selection_lists(
    monkeypatch, state, expected_kind, expected_rows
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

    assert len(sent) == 1
    assert sent[0][0] == expected_kind
    if expected_rows is not None:
        assert [row["id"] for row in sent[0][1]["rows"]] == expected_rows


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


def test_language_selection_has_one_fuel_list_and_does_not_greet_again(
    monkeypatch,
):
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
            interactive_type="button_reply",
            selection_id="lang_es",
            profile_name="Ramon",
        )
    )

    assert len(sent) == 1
    assert sent[0][0] == "list"
    assert [row["id"] for row in sent[0][1]["rows"]] == [
        "fuel_regular", "fuel_premium", "fuel_diesel", "nav_back", "nav_menu",
    ]
    assert "Hola, Ramon" not in sent[0][1]["body_text"]
    assert "bienvenido" not in sent[0][1]["body_text"].lower()


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


def test_back_from_fuel_list_returns_to_language_without_greeting(monkeypatch):
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
            interactive_type="list_reply",
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


def test_menu_row_in_sort_list_restarts_without_repeating_greeting(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        SENDER,
        state=ConversationState.WAITING_SORT,
        profile_name="Ramon",
        language="es",
        fuel_type="premium",
    )
    sent = capture_sent_prompts(monkeypatch)

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=SENDER,
            message_type="interactive",
            interactive_type="list_reply",
            selection_id="nav_menu",
        )
    )
    assert whatsapp_handler.conversation_store.get(SENDER).state == (
        ConversationState.WAITING_LANGUAGE
    )
    assert len(sent) == 1
    assert [button["id"] for button in sent[0][1]["buttons"]] == [
        "lang_en", "lang_es",
    ]
    assert "Ramon" not in sent[0][1]["body_text"]
