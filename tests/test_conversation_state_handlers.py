from app.conversation import (
    ConversationSession,
    ConversationState,
    ConversationTransitions,
    InMemoryConversationStore,
)
from app.handlers.conversation_states import ConversationStateHandlers
from app.models import IncomingMessage
from app.presentation import ListPrompt, ReplyButtonsPrompt, TextPrompt


def build_handlers():
    store = InMemoryConversationStore()
    sent = []
    handlers = ConversationStateHandlers(
        ConversationTransitions(store),
        lambda sender, prompt: sent.append((sender, prompt)),
    )
    return store, sent, handlers


def test_language_selection_shows_fuel_options_without_repeating_greeting():
    store, sent, handlers = build_handlers()

    handlers.language_selection(
        "sender",
        "es",
        display_name="Ramon",
    )

    assert store.get("sender").state == ConversationState.WAITING_FUEL
    assert isinstance(sent[0][1], ReplyButtonsPrompt)
    assert "¡Hola, Ramon!" not in sent[0][1].body_text
    assert "Para comenzar" in sent[0][1].body_text
    assert store.get("sender").profile_name == "Ramon"


def test_distance_text_converts_kilometers_and_requests_location():
    store, sent, handlers = build_handlers()
    session = store.update(
        "sender",
        state=ConversationState.WAITING_CUSTOM_DISTANCE,
        language="es",
    )

    handlers.distance_text(
        IncomingMessage(sender="sender", message_type="text", text="8 km"),
        session,
    )

    updated = store.get("sender")
    assert updated.state == ConversationState.WAITING_LOCATION
    assert updated.max_distance_miles == 4.971
    assert isinstance(sent[0][1], TextPrompt)


def test_invalid_fuel_button_repeats_expected_prompt():
    _, sent, handlers = build_handlers()
    session = ConversationSession(
        sender="sender",
        state=ConversationState.WAITING_FUEL,
        language="en",
    )

    handlers.fuel_interaction(
        IncomingMessage(
            sender="sender",
            message_type="interactive",
            selection_id="sort_price",
        ),
        session,
    )

    assert isinstance(sent[0][1], ReplyButtonsPrompt)
    assert "doesn't match" in sent[0][1].body_text


def test_custom_distance_button_changes_state_and_sends_text_prompt():
    store, sent, handlers = build_handlers()
    session = store.update(
        "sender",
        state=ConversationState.WAITING_DISTANCE,
        language="es",
    )

    handlers.distance_interaction(
        IncomingMessage(
            sender="sender",
            message_type="interactive",
            selection_id="distance_custom",
        ),
        session,
    )

    assert store.get("sender").state == (
        ConversationState.WAITING_CUSTOM_DISTANCE
    )
    assert isinstance(sent[0][1], TextPrompt)


def test_sort_without_saved_distance_sends_distance_list():
    store, sent, handlers = build_handlers()
    session = store.update(
        "sender",
        state=ConversationState.WAITING_SORT,
        language="en",
    )

    handlers.sort_interaction(
        IncomingMessage(
            sender="sender",
            message_type="interactive",
            selection_id="sort_best",
        ),
        session,
    )

    assert store.get("sender").state == ConversationState.WAITING_DISTANCE
    assert isinstance(sent[0][1], ListPrompt)
