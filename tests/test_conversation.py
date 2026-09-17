from app.conversation import (
    ConversationSession,
    ConversationState,
    InMemoryConversationStore,
)
from app.handlers import whatsapp as whatsapp_handler
from app.models import IncomingMessage


def test_conversation_store_creates_updates_and_pops_session():
    store = InMemoryConversationStore()

    new_session = store.get_or_create("15551234567")
    updated_session = store.update(
        "15551234567",
        state=ConversationState.WAITING_FUEL,
        language="es",
    )
    popped_session = store.pop("15551234567")

    assert new_session == ConversationSession(sender="15551234567")
    assert updated_session.state == ConversationState.WAITING_FUEL
    assert updated_session.language == "es"
    assert popped_session == updated_session
    assert store.get("15551234567") is None


def test_greeting_sets_waiting_language_state(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: {"messages": [{"id": "wamid.buttons"}]},
    )
    message = IncomingMessage(
        sender="15551234567",
        message_type="text",
        text="hola",
    )

    whatsapp_handler.handle_text_message(message)

    session = whatsapp_handler.conversation_store.get(message.sender)
    assert session.state == ConversationState.WAITING_LANGUAGE
    assert session.language == "en"

    whatsapp_handler.conversation_store.clear()


def test_text_preferences_set_waiting_location_state(monkeypatch):
    whatsapp_handler.conversation_store.clear()
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: {"messages": [{"id": "wamid.text"}]},
    )
    message = IncomingMessage(
        sender="15551234567",
        message_type="text",
        text="premium closest",
    )

    whatsapp_handler.handle_text_message(message)

    session = whatsapp_handler.conversation_store.get(message.sender)
    assert session == ConversationSession(
        sender=message.sender,
        state=ConversationState.WAITING_LOCATION,
        language="en",
        fuel_type="premium",
        sort="distance",
    )

    whatsapp_handler.conversation_store.clear()


def test_text_while_waiting_for_fuel_repeats_fuel_prompt(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_FUEL,
        language="es",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=sender,
            message_type="text",
            text="something else",
        )
    )

    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "fuel_regular",
        "fuel_premium",
        "fuel_diesel",
    ]
    assert "no corresponde" in sent_messages[0]["body_text"].lower()
    assert whatsapp_handler.conversation_store.get(sender).state == (
        ConversationState.WAITING_FUEL
    )

    whatsapp_handler.conversation_store.clear()


def test_location_while_waiting_for_sort_does_not_search(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_SORT,
        fuel_type="diesel",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    def unexpected_search(**kwargs):
        raise AssertionError("The gas station search should not run yet")

    monkeypatch.setattr(
        whatsapp_handler,
        "search_nearby_gas_stations",
        unexpected_search,
    )

    whatsapp_handler.handle_location_message(
        IncomingMessage(
            sender=sender,
            message_type="location",
            latitude=38.2527,
            longitude=-85.7585,
        )
    )

    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "sort_distance",
        "sort_price",
        "sort_best",
    ]
    assert whatsapp_handler.conversation_store.get(sender).state == (
        ConversationState.WAITING_SORT
    )

    whatsapp_handler.conversation_store.clear()


def test_wrong_button_while_waiting_for_language_repeats_language_prompt(
    monkeypatch,
):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_LANGUAGE,
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=sender,
            message_type="interactive",
            interactive_type="button_reply",
            selection_id="sort_price",
            selection_title="Cheapest",
        )
    )

    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "lang_en",
        "lang_es",
    ]
    assert whatsapp_handler.conversation_store.get(sender).state == (
        ConversationState.WAITING_LANGUAGE
    )

    whatsapp_handler.conversation_store.clear()


def test_image_while_waiting_for_location_repeats_location_prompt(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    expected_session = whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_text_message",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_unsupported_message(
        IncomingMessage(
            sender=sender,
            message_type="image",
            media_id="media.image",
        )
    )

    assert "esperando tu ubicación" in sent_messages[0]["message"].lower()
    assert whatsapp_handler.conversation_store.get(sender) == expected_session

    whatsapp_handler.conversation_store.clear()


def test_back_command_moves_back_and_preserves_preferences(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_LOCATION,
        language="es",
        fuel_type="premium",
        sort="price",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=sender,
            message_type="text",
            text="⬅️ Atrás",
        )
    )

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_SORT,
        language="es",
        fuel_type="premium",
        sort="price",
    )
    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "sort_distance",
        "sort_price",
        "sort_best",
    ]

    whatsapp_handler.conversation_store.clear()


def test_menu_command_resets_session(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_SORT,
        language="es",
        fuel_type="diesel",
        sort="price",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_text_message(
        IncomingMessage(
            sender=sender,
            message_type="text",
            text="🏠 Menú",
        )
    )

    assert whatsapp_handler.conversation_store.get(sender) == ConversationSession(
        sender=sender,
        state=ConversationState.WAITING_LANGUAGE,
        language="en",
        fuel_type="regular",
        sort="best",
    )
    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "lang_en",
        "lang_es",
    ]

    whatsapp_handler.conversation_store.clear()


def test_interactive_back_button_moves_from_sort_to_fuel(monkeypatch):
    sender = "15551234567"
    sent_messages = []
    whatsapp_handler.conversation_store.clear()
    whatsapp_handler.conversation_store.update(
        sender,
        state=ConversationState.WAITING_SORT,
        language="en",
        fuel_type="diesel",
    )
    monkeypatch.setattr(
        whatsapp_handler,
        "send_reply_buttons",
        lambda **kwargs: sent_messages.append(kwargs),
    )

    whatsapp_handler.handle_interactive_message(
        IncomingMessage(
            sender=sender,
            message_type="interactive",
            interactive_type="button_reply",
            selection_id="nav_back",
            selection_title="Back",
        )
    )

    assert whatsapp_handler.conversation_store.get(sender).state == (
        ConversationState.WAITING_FUEL
    )
    assert [button["id"] for button in sent_messages[0]["buttons"]] == [
        "fuel_regular",
        "fuel_premium",
        "fuel_diesel",
    ]

    whatsapp_handler.conversation_store.clear()
